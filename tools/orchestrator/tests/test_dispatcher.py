import json
import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest

from src.dag import FootprintConflict
from src.dispatcher import (
    ActiveWorktree,
    DispatcherConfig,
    RunState,
    Task,
    check_footprint_deviation,
    compute_priority_score,
    create_worktree_and_launch,
    default_dry_run_command_builder,
    load_run_state,
    notify_force_serial,
    notify_recompute,
    parse_task_from_issue,
    quota_available,
    run_dispatch_cycle,
    save_run_state,
    scan_external_locks,
    select_next_tasks,
)
from src.github import IssueRecord, PrRecord


def _issue(
    number,
    labels=("status:queued",),
    footprint=("src/foo.py",),
    symbols=("foo.Foo",),
    subtask_id="task-a",
    created_at="2026-01-01T00:00:00+00:00",
):
    footprint_lines = "\n".join(f"  - {f}" for f in footprint) if footprint else "  []"
    symbols_lines = "\n".join(f"  - {s}" for s in symbols) if symbols else "  []"
    body = (
        "## Footprint\n"
        "```yaml\n"
        f"subtask_id: {subtask_id}\n"
        "footprint:\n"
        f"{footprint_lines}\n"
        "symbols:\n"
        f"{symbols_lines}\n"
        "```\n"
    )
    return IssueRecord(
        number=number, title="t", body=body, labels=labels, created_at=created_at
    )


def _task(
    issue_number,
    priority="medium",
    risk=False,
    progress_partial=False,
    created_at="2023-01-01T00:00:00+00:00",
    footprint=("src/foo.py",),
):
    return Task(
        issue_number=issue_number,
        subtask_id=f"task-{issue_number}",
        footprint=footprint,
        symbols=(),
        risk=risk,
        priority=priority,
        progress_partial=progress_partial,
        status_labels=("status:queued",),
        created_at=created_at,
    )


class TestParseTaskFromIssue:
    def test_parses_footprint_and_symbols_from_body(self):
        issue = _issue(1, footprint=("src/foo.py", "src/bar.py"), symbols=("foo.Foo",))
        task = parse_task_from_issue(issue)
        assert task.footprint == ("src/foo.py", "src/bar.py")
        assert task.symbols == ("foo.Foo",)
        assert task.subtask_id == "task-a"

    def test_missing_footprint_block_defaults_to_empty(self):
        issue = IssueRecord(
            number=2,
            title="t",
            body="no block here",
            labels=(),
            created_at="2026-01-01T00:00:00+00:00",
        )
        task = parse_task_from_issue(issue)
        assert task.footprint == ()
        assert task.symbols == ()

    def test_priority_label_parsed(self):
        issue = _issue(3, labels=("status:queued", "priority:high"))
        assert parse_task_from_issue(issue).priority == "high"

    def test_priority_defaults_to_medium(self):
        issue = _issue(4, labels=("status:queued",))
        assert parse_task_from_issue(issue).priority == "medium"

    def test_risk_label_parsed(self):
        issue = _issue(5, labels=("status:queued", "risk:flagged"))
        assert parse_task_from_issue(issue).risk is True

    def test_progress_partial_label_parsed(self):
        issue = _issue(6, labels=("status:queued", "progress:partial"))
        assert parse_task_from_issue(issue).progress_partial is True


class TestRunState:
    def test_load_missing_file_returns_empty_state(self, tmp_path):
        state = load_run_state(tmp_path / "run_state.json")
        assert state.active_worktrees == {}
        assert state.launch_history == []

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "run_state.json"
        state = RunState(
            active_worktrees={
                "10": ActiveWorktree(
                    issue_number=10,
                    branch="claude/issue-10-x",
                    worktree_path="worktrees/claude-issue-10-x",
                    pid=12345,
                    started_at=1700000000.0,
                    declared_footprint=("src/foo.py",),
                )
            },
            launch_history=[1700000000.0],
        )
        save_run_state(state, path)
        loaded = load_run_state(path)
        assert loaded.active_worktrees["10"].branch == "claude/issue-10-x"
        assert loaded.launch_history == [1700000000.0]


class TestQuotaAvailable:
    def test_full_quota_when_state_empty(self):
        state = RunState(active_worktrees={}, launch_history=[])
        assert (
            quota_available(
                state,
                now=1_700_000_000.0,
                max_concurrent=2,
                max_launches_per_window=1,
                window_seconds=3600,
            )
            == 1
        )

    def test_zero_when_concurrent_limit_reached(self):
        state = RunState(
            active_worktrees={
                "1": ActiveWorktree(1, "b1", "w1", 1, 1_699_999_000.0, ()),
                "2": ActiveWorktree(2, "b2", "w2", 2, 1_699_999_000.0, ()),
            },
            launch_history=[],
        )
        assert (
            quota_available(
                state,
                now=1_700_000_000.0,
                max_concurrent=2,
                max_launches_per_window=5,
                window_seconds=3600,
            )
            == 0
        )

    def test_zero_when_launch_rate_exhausted_within_window(self):
        state = RunState(active_worktrees={}, launch_history=[1_699_998_000.0])
        assert (
            quota_available(
                state,
                now=1_700_000_000.0,
                max_concurrent=5,
                max_launches_per_window=1,
                window_seconds=3600,
            )
            == 0
        )

    def test_old_launches_outside_window_do_not_count(self):
        state = RunState(active_worktrees={}, launch_history=[1_699_000_000.0])
        assert (
            quota_available(
                state,
                now=1_700_000_000.0,
                max_concurrent=5,
                max_launches_per_window=1,
                window_seconds=3600,
            )
            == 1
        )


class TestComputePriorityScore:
    def test_higher_priority_scores_higher(self):
        now = 1_700_000_000.0
        low = _task(1, priority="low", created_at="2023-01-01T00:00:00+00:00")
        high = _task(2, priority="high", created_at="2023-01-01T00:00:00+00:00")
        all_tasks = [low, high]
        assert compute_priority_score(high, all_tasks, now) > compute_priority_score(
            low, all_tasks, now
        )

    def test_progress_partial_adds_flat_bonus(self):
        now = 1_700_000_000.0
        plain = _task(1, priority="medium", created_at="2023-01-01T00:00:00+00:00")
        partial = _task(
            2,
            priority="medium",
            progress_partial=True,
            created_at="2023-01-01T00:00:00+00:00",
        )
        assert compute_priority_score(
            partial, [plain, partial], now
        ) > compute_priority_score(plain, [plain, partial], now)

    def test_zero_avg_wait_does_not_raise(self):
        now = 1_700_000_000.0
        created_at = datetime.fromtimestamp(now, tz=UTC).isoformat()
        task = _task(1, created_at=created_at)  # == now, wait 0
        score = compute_priority_score(task, [task], now)
        assert score == pytest.approx(2.0)

    def test_longer_wait_scores_higher_than_shorter_wait(self):
        now = 1_700_000_000.0
        old_created = datetime.fromtimestamp(now, tz=UTC) - timedelta(days=10)
        new_created = datetime.fromtimestamp(now, tz=UTC) - timedelta(minutes=1)
        old = _task(1, created_at=old_created.isoformat())
        new = _task(2, created_at=new_created.isoformat())
        all_tasks = [old, new]
        assert compute_priority_score(old, all_tasks, now) > compute_priority_score(
            new, all_tasks, now
        )


class TestSelectNextTasks:
    def test_excludes_risk_flagged_tasks(self):
        state = RunState(active_worktrees={}, launch_history=[])
        safe = _task(1)
        risky = _task(2, risk=True, priority="high")
        selected = select_next_tasks(
            [safe, risky],
            state,
            now=1_700_000_000.0,
            max_concurrent=2,
            max_launches_per_window=2,
            window_seconds=3600,
        )
        assert risky not in selected
        assert safe in selected

    def test_excludes_already_active_issue(self):
        state = RunState(
            active_worktrees={"1": ActiveWorktree(1, "b", "w", 1, 1_699_999_000.0, ())},
            launch_history=[],
        )
        active_task = _task(1)
        other = _task(2)
        selected = select_next_tasks(
            [active_task, other],
            state,
            now=1_700_000_000.0,
            max_concurrent=5,
            max_launches_per_window=5,
            window_seconds=3600,
        )
        assert active_task not in selected
        assert other in selected

    def test_respects_quota_limit(self):
        state = RunState(active_worktrees={}, launch_history=[])
        tasks = [_task(i) for i in range(1, 5)]
        selected = select_next_tasks(
            tasks,
            state,
            now=1_700_000_000.0,
            max_concurrent=2,
            max_launches_per_window=5,
            window_seconds=3600,
        )
        assert len(selected) == 2

    def test_selects_by_descending_score_with_deterministic_tiebreak(self):
        state = RunState(active_worktrees={}, launch_history=[])
        low = _task(2, priority="low")
        high = _task(1, priority="high")
        selected = select_next_tasks(
            [low, high],
            state,
            now=1_700_000_000.0,
            max_concurrent=1,
            max_launches_per_window=5,
            window_seconds=3600,
        )
        assert selected == [high]


class TestScanExternalLocks:
    def test_locks_task_overlapping_open_pr(self):
        queued = [_task(1, footprint=("src/shared.py",))]
        prs = [
            PrRecord(number=99, head_ref="feat/other", changed_files=("src/shared.py",))
        ]
        result = scan_external_locks(
            queued, remote_branches=[], prs=prs, active_branches=[]
        )
        assert [t.issue_number for t in result.to_lock] == [1]
        assert result.to_unlock == []

    def test_does_not_lock_disjoint_footprint(self):
        queued = [_task(1, footprint=("src/unique.py",))]
        prs = [
            PrRecord(number=99, head_ref="feat/other", changed_files=("src/shared.py",))
        ]
        result = scan_external_locks(
            queued, remote_branches=[], prs=prs, active_branches=[]
        )
        assert result.to_lock == []

    def test_excludes_dispatcher_managed_branches(self):
        queued = [_task(1, footprint=("src/shared.py",))]
        prs = [
            PrRecord(
                number=99, head_ref="claude/issue-5-x", changed_files=("src/shared.py",)
            )
        ]
        result = scan_external_locks(
            queued, remote_branches=[], prs=prs, active_branches=["claude/issue-5-x"]
        )
        assert result.to_lock == []

    def test_unlocks_previously_locked_task_with_no_more_overlap(self):
        locked_task = Task(
            issue_number=1,
            subtask_id="task-1",
            footprint=("src/unique.py",),
            symbols=(),
            risk=False,
            priority="medium",
            progress_partial=False,
            status_labels=("status:external-lock",),
            created_at="2026-01-01T00:00:00+00:00",
        )
        result = scan_external_locks(
            [locked_task], remote_branches=[], prs=[], active_branches=[]
        )
        assert [t.issue_number for t in result.to_unlock] == [1]


class TestCheckFootprintDeviation:
    def test_returns_files_outside_declared_footprint(self):
        with patch("src.dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="1\t0\tsrc/foo.py\n20\t0\tsrc/unexpected.py\n",
                stderr="",
            )
            deviated = check_footprint_deviation(
                "worktrees/w1", declared_footprint=("src/foo.py",)
            )
        assert deviated == ["src/unexpected.py"]

    def test_no_deviation_returns_empty(self):
        with patch("src.dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="1\t0\tsrc/foo.py\n", stderr=""
            )
            deviated = check_footprint_deviation(
                "worktrees/w1", declared_footprint=("src/foo.py",)
            )
        assert deviated == []

    def test_small_deviation_within_buffer_is_ignored(self):
        """#200: 数行程度の微小な逸脱はライブロック防止のバッファとして無視する。"""
        with patch("src.dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="2\t1\tsrc/tiny_new_file.py\n",
                stderr="",
            )
            deviated = check_footprint_deviation(
                "worktrees/w1",
                declared_footprint=("src/foo.py",),
                min_changed_lines=5,
            )
        assert deviated == []

    def test_large_deviation_exceeding_buffer_is_reported(self):
        with patch("src.dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="10\t2\tsrc/large_new_file.py\n",
                stderr="",
            )
            deviated = check_footprint_deviation(
                "worktrees/w1",
                declared_footprint=("src/foo.py",),
                min_changed_lines=5,
            )
        assert deviated == ["src/large_new_file.py"]

    def test_binary_file_change_always_reported_regardless_of_buffer(self):
        with patch("src.dispatcher.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="-\t-\tsrc/image.png\n", stderr=""
            )
            deviated = check_footprint_deviation(
                "worktrees/w1",
                declared_footprint=(),
                min_changed_lines=100,
            )
        assert deviated == ["src/image.png"]


class TestNotifyRecompute:
    def test_dry_run_reports_without_calling_github(self):
        conflict = FootprintConflict(
            subtask_id="task-a",
            other_subtask_id="task-b",
            similarity=0.5,
            blocked_subtask_id="task-b",
        )
        with (
            patch("src.dispatcher.github.add_comment") as mock_comment,
            patch("src.dispatcher.github.add_label") as mock_label,
        ):
            bodies = notify_recompute(
                conflict,
                "作業内容の要約",
                parent_issue_number=181,
                apply=False,
                issue_number_by_subtask_id={"task-a": 1, "task-b": 2},
            )
        mock_comment.assert_not_called()
        mock_label.assert_not_called()
        assert len(bodies) >= 2

    def test_apply_posts_comments_and_labels_blocked_subtask(self):
        conflict = FootprintConflict(
            subtask_id="task-a",
            other_subtask_id="task-b",
            similarity=0.5,
            blocked_subtask_id="task-b",
        )
        with (
            patch("src.dispatcher.github.add_comment") as mock_comment,
            patch("src.dispatcher.github.add_label") as mock_label,
        ):
            notify_recompute(
                conflict,
                "作業内容の要約",
                parent_issue_number=181,
                apply=True,
                issue_number_by_subtask_id={"task-a": 1, "task-b": 2},
            )
        assert mock_comment.call_count >= 3  # task-a issue, task-b issue, parent issue
        mock_label.assert_any_call(2, "status:blocked-recompute")


class TestNotifyForceSerial:
    """#200: リトライ上限超過時の強制直列化フォールバック通知。"""

    def test_dry_run_does_not_call_github(self):
        with patch("src.dispatcher.github.add_comment") as mock_comment:
            body = notify_force_serial(
                "task-a",
                issue_number=1,
                parent_issue_number=181,
                retry_count=2,
                apply=False,
            )
        mock_comment.assert_not_called()
        assert "task-a" in body

    def test_apply_posts_comment_to_parent_issue(self):
        with patch("src.dispatcher.github.add_comment") as mock_comment:
            notify_force_serial(
                "task-a",
                issue_number=1,
                parent_issue_number=181,
                retry_count=2,
                apply=True,
            )
        mock_comment.assert_called_once_with(181, ANY)

    def test_apply_without_parent_issue_skips_comment(self):
        with patch("src.dispatcher.github.add_comment") as mock_comment:
            notify_force_serial(
                "task-a",
                issue_number=1,
                parent_issue_number=None,
                retry_count=2,
                apply=True,
            )
        mock_comment.assert_not_called()


class TestCreateWorktreeAndLaunch:
    def test_dry_run_does_not_call_subprocess(self, tmp_path):
        task = _task(1)
        with (
            patch("src.dispatcher.subprocess.run") as mock_run,
            patch("src.dispatcher.subprocess.Popen") as mock_popen,
        ):
            result = create_worktree_and_launch(
                task,
                branch_name="claude/issue-1-task-1",
                worktree_root=tmp_path / "worktrees",
                log_dir=tmp_path / "logs",
                command_builder=default_dry_run_command_builder,
                apply=False,
            )
        mock_run.assert_not_called()
        mock_popen.assert_not_called()
        assert result.launched is False

    def test_apply_creates_worktree_and_launches_process(self, tmp_path):
        task = _task(1)
        with (
            patch("src.dispatcher.subprocess.run") as mock_run,
            patch("src.dispatcher.subprocess.Popen") as mock_popen,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            mock_popen.return_value.pid = 4242
            result = create_worktree_and_launch(
                task,
                branch_name="claude/issue-1-task-1",
                worktree_root=tmp_path / "worktrees",
                log_dir=tmp_path / "logs",
                command_builder=default_dry_run_command_builder,
                apply=True,
            )
        assert mock_run.called
        assert mock_popen.called
        assert result.launched is True
        assert result.pid == 4242

    def test_rejects_invalid_branch_name(self, tmp_path):
        task = _task(1)
        with pytest.raises(ValueError):
            create_worktree_and_launch(
                task,
                branch_name="--upload-pack=evil",
                worktree_root=tmp_path / "worktrees",
                log_dir=tmp_path / "logs",
                command_builder=default_dry_run_command_builder,
                apply=True,
            )


class TestRunDispatchCycle:
    def test_dry_run_makes_no_write_calls(self, tmp_path):
        config = DispatcherConfig(
            max_concurrent=2,
            max_launches_per_window=2,
            window_seconds=3600,
            run_state_path=tmp_path / "run_state.json",
            worktree_root=tmp_path / "worktrees",
            log_dir=tmp_path / "logs",
            apply=False,
        )
        queued_issue = _issue(1)
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.remove_label") as mock_remove_label,
            patch("src.dispatcher.subprocess.run") as mock_subproc_run,
            patch("src.dispatcher.subprocess.Popen") as mock_popen,
        ):
            mock_list.side_effect = (
                lambda label: [queued_issue] if label == "status:queued" else []
            )
            report = run_dispatch_cycle(config)

        mock_add_label.assert_not_called()
        mock_remove_label.assert_not_called()
        mock_subproc_run.assert_not_called()
        mock_popen.assert_not_called()
        assert report.applied is False
        assert len(report.selected) == 1
        assert not (tmp_path / "run_state.json").exists()

    def test_apply_launches_selected_task_and_persists_state(self, tmp_path):
        config = DispatcherConfig(
            max_concurrent=2,
            max_launches_per_window=2,
            window_seconds=3600,
            run_state_path=tmp_path / "run_state.json",
            worktree_root=tmp_path / "worktrees",
            log_dir=tmp_path / "logs",
            apply=True,
        )
        queued_issue = _issue(1)
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.remove_label"),
            patch("src.dispatcher.subprocess.run") as mock_subproc_run,
            patch("src.dispatcher.subprocess.Popen") as mock_popen,
        ):
            mock_list.side_effect = (
                lambda label: [queued_issue] if label == "status:queued" else []
            )
            mock_subproc_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            mock_popen.return_value.pid = 555
            report = run_dispatch_cycle(config)

        assert report.applied is True
        assert len(report.selected) == 1
        mock_add_label.assert_any_call(1, "status:in-progress")
        assert (tmp_path / "run_state.json").exists()
        persisted = json.loads((tmp_path / "run_state.json").read_text())
        assert "1" in persisted["active_worktrees"]

    def test_quota_exhausted_selects_nothing(self, tmp_path):
        run_state_path = tmp_path / "run_state.json"
        save_run_state(
            RunState(
                active_worktrees={
                    "9": ActiveWorktree(9, "b", "w", 1, 1_699_999_000.0, ()),
                    "8": ActiveWorktree(8, "b2", "w2", 2, 1_699_999_000.0, ()),
                },
                launch_history=[],
            ),
            run_state_path,
        )
        config = DispatcherConfig(
            max_concurrent=2,
            max_launches_per_window=5,
            window_seconds=3600,
            run_state_path=run_state_path,
            worktree_root=tmp_path / "worktrees",
            log_dir=tmp_path / "logs",
            apply=False,
        )
        queued_issue = _issue(1)
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
        ):
            mock_list.side_effect = (
                lambda label: [queued_issue] if label == "status:queued" else []
            )
            report = run_dispatch_cycle(config)

        assert report.selected == []
        assert report.quota_slots_available == 0


class TestRunDispatchCycleFootprintRecompute:
    """#192: footprint逸脱検知 → DAG再計算 → notify_recompute の配線。"""

    def _config(self, tmp_path, run_state_path, **overrides):
        defaults = dict(
            max_concurrent=2,
            max_launches_per_window=2,
            window_seconds=3600,
            run_state_path=run_state_path,
            worktree_root=tmp_path / "worktrees",
            log_dir=tmp_path / "logs",
            apply=True,
            parent_issue_number=181,
        )
        defaults.update(overrides)
        return DispatcherConfig(**defaults)

    def test_significant_deviation_triggers_recompute_and_notify(self, tmp_path):
        run_state_path = tmp_path / "run_state.json"
        save_run_state(
            RunState(
                active_worktrees={
                    "1": ActiveWorktree(
                        issue_number=1,
                        branch="claude/issue-1-task-a",
                        worktree_path=str(tmp_path / "w1"),
                        pid=111,
                        started_at=1_699_999_000.0,
                        declared_footprint=("src/foo.py",),
                    )
                },
                launch_history=[],
            ),
            run_state_path,
        )
        config = self._config(tmp_path, run_state_path)
        in_progress_issue = _issue(
            1,
            labels=("status:in-progress",),
            footprint=("src/foo.py",),
            symbols=("foo.Foo",),
            subtask_id="task-a",
        )
        conflict = FootprintConflict(
            subtask_id="task-a",
            other_subtask_id="task-b",
            similarity=0.5,
            blocked_subtask_id="task-b",
        )
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.remove_label"),
            patch("src.dispatcher.subprocess.Popen"),
            patch(
                "src.dispatcher.check_footprint_deviation",
                return_value=["src/unexpected.py"],
            ) as mock_check_deviation,
            patch(
                "src.dispatcher.recompute_dag_for_footprint_change"
            ) as mock_recompute,
            patch(
                "src.dispatcher.notify_recompute", return_value=["body"]
            ) as mock_notify,
        ):
            mock_list.side_effect = (
                lambda label: [in_progress_issue]
                if label == "status:in-progress"
                else []
            )
            mock_recompute.return_value = (MagicMock(), [conflict])

            report = run_dispatch_cycle(config)

        mock_add_label.assert_not_called()
        mock_check_deviation.assert_called_once()
        mock_recompute.assert_called_once()
        assert mock_recompute.call_args.args[1] == "task-a"
        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["apply"] is True
        assert len(report.deviation_events) == 1
        event = report.deviation_events[0]
        assert event["issue_number"] == 1
        assert event["action"] == "recomputed"
        assert event["deviated_files"] == ["src/unexpected.py"]

        persisted = json.loads(run_state_path.read_text())
        assert persisted["active_worktrees"]["1"]["recompute_count"] == 1

    def test_dry_run_recompute_does_not_persist_or_call_github(self, tmp_path):
        run_state_path = tmp_path / "run_state.json"
        save_run_state(
            RunState(
                active_worktrees={
                    "1": ActiveWorktree(
                        issue_number=1,
                        branch="claude/issue-1-task-a",
                        worktree_path=str(tmp_path / "w1"),
                        pid=111,
                        started_at=1_699_999_000.0,
                        declared_footprint=("src/foo.py",),
                    )
                },
                launch_history=[],
            ),
            run_state_path,
        )
        config = self._config(tmp_path, run_state_path, apply=False)
        in_progress_issue = _issue(
            1, labels=("status:in-progress",), subtask_id="task-a"
        )
        conflict = FootprintConflict(
            subtask_id="task-a",
            other_subtask_id="task-b",
            similarity=0.5,
            blocked_subtask_id="task-b",
        )
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.add_comment") as mock_add_comment,
            patch(
                "src.dispatcher.check_footprint_deviation",
                return_value=["src/unexpected.py"],
            ),
            patch(
                "src.dispatcher.recompute_dag_for_footprint_change"
            ) as mock_recompute,
            patch(
                "src.dispatcher.notify_recompute", return_value=["dry body"]
            ) as mock_notify,
        ):
            mock_list.side_effect = (
                lambda label: [in_progress_issue]
                if label == "status:in-progress"
                else []
            )
            mock_recompute.return_value = (MagicMock(), [conflict])

            run_dispatch_cycle(config)

        mock_add_label.assert_not_called()
        mock_add_comment.assert_not_called()
        assert mock_notify.call_args.kwargs["apply"] is False

        persisted = json.loads(run_state_path.read_text())
        assert persisted["active_worktrees"]["1"]["recompute_count"] == 0

    def test_retry_limit_exceeded_triggers_forced_serialization(self, tmp_path):
        """#200: リトライ上限超過時は再計算せず強制直列化にフォールバックする。"""
        run_state_path = tmp_path / "run_state.json"
        save_run_state(
            RunState(
                active_worktrees={
                    "1": ActiveWorktree(
                        issue_number=1,
                        branch="claude/issue-1-task-a",
                        worktree_path=str(tmp_path / "w1"),
                        pid=111,
                        started_at=1_699_999_000.0,
                        declared_footprint=("src/foo.py",),
                        recompute_count=2,
                    )
                },
                launch_history=[],
            ),
            run_state_path,
        )
        config = self._config(tmp_path, run_state_path, max_recompute_retries=2)
        in_progress_issue = _issue(
            1, labels=("status:in-progress",), subtask_id="task-a"
        )
        other_queued_issue = _issue(2, labels=("status:queued",), subtask_id="task-b")
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.remove_label"),
            patch("src.dispatcher.github.add_comment") as mock_add_comment,
            patch(
                "src.dispatcher.check_footprint_deviation",
                return_value=["src/unexpected.py"],
            ),
            patch(
                "src.dispatcher.recompute_dag_for_footprint_change"
            ) as mock_recompute,
        ):

            def _list(label):
                if label == "status:queued":
                    return [other_queued_issue]
                if label == "status:in-progress":
                    return [in_progress_issue]
                return []

            mock_list.side_effect = _list

            report = run_dispatch_cycle(config)

        mock_recompute.assert_not_called()
        mock_add_label.assert_any_call(1, "status:force-serial")
        mock_add_comment.assert_called_once()
        assert report.selected == []
        assert report.deviation_events[0]["action"] == "forced_serial"

        persisted = json.loads(run_state_path.read_text())
        assert persisted["active_worktrees"]["1"]["forced_serial"] is True

    def test_already_forced_serial_does_not_recompute_again(self, tmp_path):
        """一度強制直列化された後は、再度の再計算・通知でチャーンさせない。"""
        run_state_path = tmp_path / "run_state.json"
        save_run_state(
            RunState(
                active_worktrees={
                    "1": ActiveWorktree(
                        issue_number=1,
                        branch="claude/issue-1-task-a",
                        worktree_path=str(tmp_path / "w1"),
                        pid=111,
                        started_at=1_699_999_000.0,
                        declared_footprint=("src/foo.py",),
                        recompute_count=2,
                        forced_serial=True,
                    )
                },
                launch_history=[],
            ),
            run_state_path,
        )
        config = self._config(tmp_path, run_state_path, max_recompute_retries=2)
        in_progress_issue = _issue(
            1, labels=("status:in-progress",), subtask_id="task-a"
        )
        with (
            patch("src.dispatcher.github.list_issues_by_label") as mock_list,
            patch("src.dispatcher.github.list_remote_branches", return_value=[]),
            patch("src.dispatcher.github.list_open_prs", return_value=[]),
            patch("src.dispatcher.github.add_label") as mock_add_label,
            patch("src.dispatcher.github.add_comment") as mock_add_comment,
            patch(
                "src.dispatcher.check_footprint_deviation",
                return_value=["src/unexpected.py"],
            ),
            patch(
                "src.dispatcher.recompute_dag_for_footprint_change"
            ) as mock_recompute,
        ):
            mock_list.side_effect = (
                lambda label: [in_progress_issue]
                if label == "status:in-progress"
                else []
            )
            report = run_dispatch_cycle(config)

        mock_recompute.assert_not_called()
        mock_add_comment.assert_not_called()
        mock_add_label.assert_not_called()
        assert report.selected == []
        assert report.deviation_events[0]["action"] == "already_forced_serial"
