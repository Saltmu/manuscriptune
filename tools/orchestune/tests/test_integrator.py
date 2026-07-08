from __future__ import annotations

import subprocess
from unittest.mock import patch

from src.github import IssueRecord
from src.integrator import Integrator, IntegratorConfig


def _issue(
    number: int,
    labels: tuple[str, ...] = (),
    subtask_id: str = "",
    depends_on: tuple[str, ...] = (),
) -> IssueRecord:
    body = "```yaml\n"
    if subtask_id:
        body += f"subtask_id: {subtask_id}\n"
    if depends_on:
        body += "depends_on:\n"
        for dep in depends_on:
            body += f"  - {dep}\n"
    body += "```\n"
    return IssueRecord(
        number=number,
        title=f"Test Issue {number}",
        body=body,
        labels=labels,
        created_at="2026-07-07T00:00:00Z",
    )


class TestIntegrator:
    @patch("src.integrator.github.list_issues_by_label")
    def test_no_done_tasks(self, mock_list):
        mock_list.return_value = []
        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()
        assert res["status"] == "no_done_tasks"

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_success_integration(self, mock_run, mock_list):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        issue_b = _issue(
            2, labels=("status:done",), subtask_id="task-2", depends_on=("task-1",)
        )

        def list_side_effect(label, *args, **kwargs):
            if label == "status:done":
                return [issue_b, issue_a]
            return [issue_a, issue_b]

        mock_list.side_effect = list_side_effect

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )

        config = IntegratorConfig(apply=True, parent_issue_number=100)
        integrator = Integrator(config)

        with patch("src.integrator.github.add_comment") as mock_comment:
            res = integrator.run()

        assert res["status"] == "success"
        assert res["merged"] == ["task-1", "task-2"]

        merge_calls = [
            call for call in mock_run.call_args_list if "merge" in call.args[0]
        ]
        assert len(merge_calls) == 2
        assert any("claude/issue-1-task-1" in arg for arg in merge_calls[0].args[0])
        assert any("claude/issue-2-task-2" in arg for arg in merge_calls[1].args[0])

        mock_comment.assert_called_once()
        assert (
            "🎉 すべての完了タスク (task-1, task-2) の仮マージCIが正常に通過しました。"
            in mock_comment.call_args[0][1]
        )

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    @patch("src.integrator.github.remove_label")
    @patch("src.integrator.github.add_label")
    @patch("src.integrator.github.add_comment")
    def test_merge_conflict_failure(
        self, mock_comment, mock_add, mock_remove, mock_run, mock_list
    ):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")

        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        def run_side_effect(args, **kwargs):
            if "checkout" in args:
                return subprocess.CompletedProcess(args=args, returncode=0)
            if "merge" in args:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=args, stderr=b"CONFLICT (content): Merge conflict"
                )
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)

        res = integrator.run()

        assert res["status"] == "failure"
        assert "task-1" in res["failed"]

        mock_remove.assert_called_with(1, "status:done")
        mock_add.assert_called_with(1, "status:queued")
        mock_comment.assert_called_once()
        assert "Merge conflict" in mock_comment.call_args[0][1]

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    @patch("src.integrator.github.remove_label")
    @patch("src.integrator.github.add_label")
    @patch("src.integrator.github.add_comment")
    def test_ci_failure_recovery(
        self, mock_comment, mock_add, mock_remove, mock_run, mock_list
    ):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        def run_side_effect(args, **kwargs):
            if "local-ci.sh" in args[0] or "local-ci.sh" in args:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=args, stderr=b"CI fail"
                )
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "failure"
        assert "task-1" in res["failed"]

        reset_calls = [
            call for call in mock_run.call_args_list if "reset" in call.args[0]
        ]
        assert len(reset_calls) == 1
        assert "HEAD~1" in reset_calls[0].args[0]

        mock_remove.assert_called_with(1, "status:done")
        mock_add.assert_called_with(1, "status:queued")
        assert "CI verification failed" in mock_comment.call_args[0][1]

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_fetches_branch_with_explicit_refspec_before_merge(
        self, mock_run, mock_list
    ):
        # actions/checkout@v6 のデフォルト（単一ブランチの浅いclone）では
        # `git fetch origin <branch>`（refspec省略）だけでは
        # `origin/<branch>` のremote-trackingブランチが作成されないため、
        # 明示的な refspec 付きでfetchしてからマージする必要がある。
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "success"

        fetch_calls = [
            call for call in mock_run.call_args_list if "fetch" in call.args[0]
        ]
        assert len(fetch_calls) == 1
        assert fetch_calls[0].args[0] == [
            "git",
            "fetch",
            "origin",
            "claude/issue-1-task-1:refs/remotes/origin/claude/issue-1-task-1",
        ]

        fetch_index = mock_run.call_args_list.index(fetch_calls[0])
        merge_index = next(
            i
            for i, call in enumerate(mock_run.call_args_list)
            if "merge" in call.args[0] and "--no-ff" in call.args[0]
        )
        assert fetch_index < merge_index

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_unshallows_repository_before_merging_when_shallow(
        self, mock_run, mock_list
    ):
        # actions/checkout@v6 のデフォルト（浅いclone）のままタスクブランチを
        # fetchすると、そのコミットも親を持たない浅い状態になり、mainとの共通の
        # 祖先が見つからず『refusing to merge unrelated histories』でmergeが
        # 必ず失敗するため、浅いリポジトリの場合は事前に履歴を深くする必要がある。
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        def run_side_effect(args, **kwargs):
            if args[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout=b"true\n", stderr=b""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=b"", stderr=b""
            )

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "success"

        unshallow_calls = [
            call for call in mock_run.call_args_list if "--unshallow" in call.args[0]
        ]
        assert len(unshallow_calls) == 1
        assert unshallow_calls[0].args[0] == [
            "git",
            "fetch",
            "--unshallow",
            "origin",
            "main",
        ]

        unshallow_index = mock_run.call_args_list.index(unshallow_calls[0])
        branch_fetch_index = next(
            i
            for i, call in enumerate(mock_run.call_args_list)
            if call.args[0]
            == [
                "git",
                "fetch",
                "origin",
                "claude/issue-1-task-1:refs/remotes/origin/claude/issue-1-task-1",
            ]
        )
        assert unshallow_index < branch_fetch_index

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_skips_unshallow_when_repository_is_not_shallow(self, mock_run, mock_list):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        def run_side_effect(args, **kwargs):
            if args[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout=b"false\n", stderr=b""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=b"", stderr=b""
            )

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "success"

        unshallow_calls = [
            call for call in mock_run.call_args_list if "--unshallow" in call.args[0]
        ]
        assert len(unshallow_calls) == 0

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    @patch("src.integrator.github.remove_label")
    @patch("src.integrator.github.add_label")
    @patch("src.integrator.github.add_comment")
    def test_fetch_failure_is_handled_like_merge_failure(
        self, mock_comment, mock_add, mock_remove, mock_run, mock_list
    ):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        def run_side_effect(args, **kwargs):
            if "fetch" in args:
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args,
                    stderr=b"fatal: couldn't find remote ref claude/issue-1-task-1",
                )
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "failure"
        assert "task-1" in res["failed"]

        merge_calls = [
            call
            for call in mock_run.call_args_list
            if "merge" in call.args[0] and "--no-ff" in call.args[0]
        ]
        assert len(merge_calls) == 0

        mock_remove.assert_called_with(1, "status:done")
        mock_add.assert_called_with(1, "status:queued")

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    @patch("src.integrator.github.remove_label")
    @patch("src.integrator.github.add_label")
    @patch("src.integrator.github.add_comment")
    def test_merge_conflict_aborts_before_next_task(
        self, mock_comment, mock_add, mock_remove, mock_run, mock_list
    ):
        # task-1 のマージがコンフリクトで失敗しても、task-2 は巻き添えを受けず
        # クリーンな状態から正常にマージ・統合されるべき。
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        issue_b = _issue(2, labels=("status:done",), subtask_id="task-2")

        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a, issue_b]

        def run_side_effect(args, **kwargs):
            if "merge" in args and any("claude/issue-1-task-1" in a for a in args):
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args,
                    stderr=b"CONFLICT (content): Merge conflict",
                )
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)

        res = integrator.run()

        assert res["status"] == "partial_success"
        assert res["merged"] == ["task-2"]
        assert res["failed"] == ["task-1"]

        abort_calls = [
            call
            for call in mock_run.call_args_list
            if "merge" in call.args[0] and "--abort" in call.args[0]
        ]
        assert len(abort_calls) == 1

        merge_call_indices = [
            i
            for i, call in enumerate(mock_run.call_args_list)
            if "merge" in call.args[0] and "--no-ff" in call.args[0]
        ]
        abort_call_index = mock_run.call_args_list.index(abort_calls[0])
        # abort は task-1 のマージ失敗の直後、task-2 のマージ試行より前に呼ばれる
        assert merge_call_indices[0] < abort_call_index < merge_call_indices[1]

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_ci_flaky_handling(self, mock_run, mock_list):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        mock_list.side_effect = lambda label, *args, **kwargs: [issue_a]

        ci_calls = 0

        def run_side_effect(args, **kwargs):
            nonlocal ci_calls
            if "local-ci.sh" in args[0] or "local-ci.sh" in args:
                ci_calls += 1
                if ci_calls == 1:
                    raise subprocess.CalledProcessError(returncode=1, cmd=args)
                return subprocess.CompletedProcess(args=args, returncode=0)
            return subprocess.CompletedProcess(args=args, returncode=0)

        mock_run.side_effect = run_side_effect

        config = IntegratorConfig(apply=True, max_flaky_retries=2)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "success"
        assert res["merged"] == ["task-1"]
        assert ci_calls == 2

    @patch("src.integrator.github.list_issues_by_label")
    @patch("src.integrator.subprocess.run")
    def test_integration_with_closed_done_task(self, mock_run, mock_list):
        issue_a = _issue(1, labels=("status:done",), subtask_id="task-1")
        issue_b = _issue(
            2, labels=("status:done",), subtask_id="task-2", depends_on=("task-1",)
        )

        def list_side_effect(label, state="open"):
            if label == "status:done":
                if state == "all":
                    return [issue_a, issue_b]
                else:
                    return [issue_b]
            return []

        mock_list.side_effect = list_side_effect

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )

        config = IntegratorConfig(apply=True)
        integrator = Integrator(config)
        res = integrator.run()

        assert res["status"] == "success"
        assert res["merged"] == ["task-1", "task-2"]
