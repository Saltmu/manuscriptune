import subprocess
from unittest.mock import patch

from src.dispatch_gc import (
    _finalize_not_needed_worktree,
    is_process_alive,
    remove_worktree,
    worktree_has_uncommitted_changes,
)
from src.dispatch_scoring import Task
from src.dispatch_state import ActiveWorktree
from src.dispatcher import DispatcherConfig


def _active(**overrides):
    defaults = dict(
        issue_number=280,
        branch="claude/issue-280-task-a",
        worktree_path="worktrees/w1",
        pid=111,
        started_at=1_699_999_000.0,
        declared_footprint=("src/foo.py",),
    )
    defaults.update(overrides)
    return ActiveWorktree(**defaults)


def _task(**overrides):
    defaults = dict(
        issue_number=280,
        subtask_id="task-a",
        footprint=("src/foo.py",),
        symbols=(),
        risk=False,
        priority="medium",
        progress_partial=False,
        status_labels=("status:not-needed",),
        created_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return Task(**defaults)


class TestIsProcessAlive:
    """#193: pidのプロセス生存確認による完了判定。"""

    def test_none_pid_is_not_alive(self):
        assert is_process_alive(None) is False

    def test_alive_pid_returns_true(self):
        with patch("src.dispatch_gc.os.kill") as mock_kill:
            mock_kill.return_value = None
            assert is_process_alive(12345) is True

    def test_missing_pid_returns_false(self):
        with patch("src.dispatch_gc.os.kill", side_effect=ProcessLookupError):
            assert is_process_alive(12345) is False

    def test_permission_error_is_treated_as_alive(self):
        with patch("src.dispatch_gc.os.kill", side_effect=PermissionError):
            assert is_process_alive(1) is True


class TestWorktreeHasUncommittedChanges:
    """#193: worktree削除前の未コミット変更確認（安全側フォールバック）。"""

    def test_clean_worktree_returns_false(self):
        with patch("src.dispatch_gc.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert worktree_has_uncommitted_changes("worktrees/w1") is False

    def test_dirty_worktree_returns_true(self):
        with patch("src.dispatch_gc.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=" M src/foo.py\n", stderr=""
            )
            assert worktree_has_uncommitted_changes("worktrees/w1") is True

    def test_git_error_defaults_to_clean(self):
        """存在しないworktreeなどgit statusが失敗する場合はクオータ解放を優先し、
        削除を妨げないようクリーン扱いとする。"""
        with patch(
            "src.dispatch_gc.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, []),
        ):
            assert worktree_has_uncommitted_changes("worktrees/missing") is False


class TestRemoveWorktree:
    """#193: 完了したworktreeの削除。"""

    def test_calls_git_worktree_remove_without_force(self):
        with patch("src.dispatch_gc.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            remove_worktree("worktrees/w1")
        args = mock_run.call_args.args[0]
        assert args == ["git", "worktree", "remove", "worktrees/w1"]
        assert "--force" not in args

    def test_swallows_error_when_already_removed(self):
        with patch(
            "src.dispatch_gc.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, []),
        ):
            remove_worktree("worktrees/already-gone")  # 例外を送出しないこと


class TestFinalizeNotNeededWorktree:
    """#280: status:not-neededラベル検知による完全自動クローズ。"""

    def test_apply_removes_worktree_and_closes_issue(self):
        active = _active()
        task = _task()
        config = DispatcherConfig(apply=True)
        with (
            patch(
                "src.dispatch_gc.worktree_has_uncommitted_changes", return_value=False
            ),
            patch("src.dispatch_gc.remove_worktree") as mock_remove_worktree,
            patch("src.dispatch_gc.github.remove_label") as mock_remove_label,
            patch("src.dispatch_gc.github.close_issue") as mock_close_issue,
        ):
            event = _finalize_not_needed_worktree(active, task, config)

        mock_remove_worktree.assert_called_once_with("worktrees/w1")
        mock_remove_label.assert_called_once_with(280, "status:in-progress")
        mock_close_issue.assert_called_once()
        close_args = mock_close_issue.call_args.args
        assert close_args[0] == 280
        assert close_args[1] == "not planned"
        assert event == {
            "issue_number": 280,
            "worktree_path": "worktrees/w1",
            "action": "not_needed",
            "subtask_id": "task-a",
        }

    def test_dirty_worktree_is_not_closed(self):
        """未コミットの作業が残っている場合は、安全側に倒しクローズを見送る。"""
        active = _active()
        task = _task()
        config = DispatcherConfig(apply=True)
        with (
            patch(
                "src.dispatch_gc.worktree_has_uncommitted_changes", return_value=True
            ),
            patch("src.dispatch_gc.remove_worktree") as mock_remove_worktree,
            patch("src.dispatch_gc.github.remove_label") as mock_remove_label,
            patch("src.dispatch_gc.github.close_issue") as mock_close_issue,
        ):
            event = _finalize_not_needed_worktree(active, task, config)

        mock_remove_worktree.assert_not_called()
        mock_remove_label.assert_not_called()
        mock_close_issue.assert_not_called()
        assert event["action"] == "completion_skipped_dirty_worktree"

    def test_dry_run_does_not_call_github_or_mutate(self):
        active = _active()
        task = _task()
        config = DispatcherConfig(apply=False)
        with (
            patch(
                "src.dispatch_gc.worktree_has_uncommitted_changes", return_value=False
            ),
            patch("src.dispatch_gc.remove_worktree") as mock_remove_worktree,
            patch("src.dispatch_gc.github.remove_label") as mock_remove_label,
            patch("src.dispatch_gc.github.close_issue") as mock_close_issue,
        ):
            event = _finalize_not_needed_worktree(active, task, config)

        mock_remove_worktree.assert_not_called()
        mock_remove_label.assert_not_called()
        mock_close_issue.assert_not_called()
        assert event["action"] == "not_needed"

    def test_none_task_defaults_subtask_id_to_empty_string(self):
        active = _active()
        config = DispatcherConfig(apply=True)
        with (
            patch(
                "src.dispatch_gc.worktree_has_uncommitted_changes", return_value=False
            ),
            patch("src.dispatch_gc.remove_worktree"),
            patch("src.dispatch_gc.github.remove_label"),
            patch("src.dispatch_gc.github.close_issue"),
        ):
            event = _finalize_not_needed_worktree(active, None, config)
        assert event["subtask_id"] == ""
