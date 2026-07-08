from datetime import UTC, datetime, timedelta

import pytest

from src.dispatch_scoring import (
    Task,
    compute_priority_score,
    parse_task_from_issue,
    quota_available,
    select_next_tasks,
)
from src.dispatch_state import ActiveWorktree, RunState
from src.github import IssueRecord


def _issue(
    number,
    labels=("status:queued",),
    footprint=("src/foo.py",),
    symbols=("foo.Foo",),
    subtask_id="task-a",
    depends_on=(),
    created_at="2026-01-01T00:00:00+00:00",
):
    footprint_lines = "\n".join(f"  - {f}" for f in footprint) if footprint else "  []"
    symbols_lines = "\n".join(f"  - {s}" for s in symbols) if symbols else "  []"
    depends_on_lines = (
        "\n".join(f"  - {d}" for d in depends_on) if depends_on else "  []"
    )
    body = (
        "## Footprint\n"
        "```yaml\n"
        f"subtask_id: {subtask_id}\n"
        "footprint:\n"
        f"{footprint_lines}\n"
        "symbols:\n"
        f"{symbols_lines}\n"
        "depends_on:\n"
        f"{depends_on_lines}\n"
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
    depends_on=(),
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
        depends_on=depends_on,
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

    def test_depends_on_parsed_from_body(self):
        issue = _issue(7, depends_on=("task-a", "task-b"))
        assert parse_task_from_issue(issue).depends_on == ("task-a", "task-b")

    def test_missing_depends_on_defaults_to_empty(self):
        issue = IssueRecord(
            number=8,
            title="t",
            body="no block here",
            labels=(),
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert parse_task_from_issue(issue).depends_on == ()

    def test_invalid_yaml_sets_yaml_error(self):
        body = (
            "## Footprint\n"
            "```yaml\n"
            "subtask_id: task-invalid\n"
            "footprint:\n"
            "  - [invalid-yaml-structure:\n"
            "```\n"
        )
        issue = IssueRecord(
            number=9,
            title="t",
            body=body,
            labels=(),
            created_at="2026-01-01T00:00:00+00:00",
        )
        task = parse_task_from_issue(issue)
        assert task.yaml_error is True
        assert task.subtask_id == ""


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
