from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src import github
from src.dag import SubTask, build_dag
from src.dispatcher import Task, parse_task_from_issue
from src.integration_coordinator import IntegrationCoordinator, record_pending_review


@dataclass
class IntegratorConfig:
    repository_root: Path = Path(".")
    base_branch: str = "origin/main"
    temp_branch: str = "integration/temp-main"
    ci_command: list[str] | None = None
    max_flaky_retries: int = 2
    parent_issue_number: int | None = None
    apply: bool = False
    # #186: CI通過後のLLM統合コーディネーターによる意味的レビュー。
    # 当初構想どおり既定ON。ただし`coordinator`が注入されている場合のみ実行され、
    # 未注入なら安全にスキップされる（`run()`のガードを参照）。
    enable_semantic_review: bool = True
    coordinator: IntegrationCoordinator | None = None
    review_state_path: Path = Path("integration_review_state.json")


class Integrator:
    def __init__(self, config: IntegratorConfig):
        self.config = config
        if self.config.ci_command is None:
            self.config.ci_command = ["./scripts/local-ci.sh"]

    def run(self) -> dict:
        sorted_done_tasks = self._get_sorted_done_tasks()
        if not sorted_done_tasks:
            return {"status": "no_done_tasks", "merged": []}

        temp_worktree_path = None
        if self.config.apply:
            temp_worktree_path = (
                self.config.repository_root / "worktrees" / "integration-temp"
            )
            try:
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(self.config.repository_root),
                    capture_output=True,
                )
                if temp_worktree_path.exists():
                    import shutil

                    try:
                        shutil.rmtree(temp_worktree_path)
                    except Exception:
                        pass
                subprocess.run(
                    [
                        "git",
                        "worktree",
                        "add",
                        str(temp_worktree_path),
                        self.config.base_branch,
                    ],
                    cwd=str(self.config.repository_root),
                    check=True,
                    capture_output=True,
                )
                self.config.repository_root = temp_worktree_path
            except (subprocess.CalledProcessError, OSError) as e:
                return {
                    "status": "failed_to_create_temp_worktree",
                    "error": f"Failed to create temp worktree: {e}",
                }

        try:
            if not self._create_temp_branch():
                return {
                    "status": "failed_to_create_temp_branch",
                    "error": "Failed to create temp branch",
                }

            merged_tasks, failed_tasks = self._merge_and_test_tasks(sorted_done_tasks)

            if merged_tasks and not failed_tasks:
                if self.config.apply:
                    try:
                        subprocess.run(
                            [
                                "git",
                                "push",
                                "--force",
                                "origin",
                                self.config.temp_branch,
                            ],
                            cwd=str(self.config.repository_root),
                            check=True,
                            capture_output=True,
                        )
                    except subprocess.CalledProcessError as pe:
                        print(
                            f"Warning: Failed to push temp branch: {pe.stderr.decode()}",
                            file=sys.stderr,
                        )

                    # #186: 意味的レビューが有効なら、dispatcherと同一のルーチンを起動して
                    # レビューを委譲する。合否はレビューセッションが親Issueへラベル付与で
                    # 伝え、実際のPRマージはPython側(process_pending_reviews)が後続サイクルで
                    # 決定論的に実行する（レビューセッション自身はマージしない）。
                    if (
                        self.config.enable_semantic_review
                        and self.config.coordinator is not None
                        and self.config.parent_issue_number
                    ):
                        new_subtask_prs = self._resolve_open_prs_for_merge(
                            sorted_done_tasks, merged_tasks
                        )
                        if new_subtask_prs:
                            new_subtask_ids = [sid for sid, _, _ in new_subtask_prs]
                            handle = self.config.coordinator.dispatch_review(
                                temp_branch=self.config.temp_branch,
                                base_branch=self.config.base_branch,
                                parent_issue_number=self.config.parent_issue_number,
                                merged_subtask_ids=new_subtask_ids,
                            )
                            record_pending_review(
                                self.config.review_state_path,
                                parent_issue_number=self.config.parent_issue_number,
                                subtask_prs=new_subtask_prs,
                                session_handle=handle,
                            )
                            github.add_comment(
                                self.config.parent_issue_number,
                                f"🔍 完了タスク ({', '.join(new_subtask_ids)}) の仮マージCIが通過したため、"
                                "統合コーディネーターによる意味的レビューを開始しました。\n"
                                "問題なければサブタスクPRは自動マージされ、問題があれば該当サブタスクが"
                                "差し戻されます（この判定・実行を除き、最終的なマージ操作は"
                                "すべてPython側が決定論的に行います）。\n"
                                f"レビューセッション: {handle.external_url or '(URL不明)'}",
                            )
                            return {
                                "status": "semantic_review_dispatched",
                                "merged": new_subtask_ids,
                                "review_session_url": handle.external_url,
                            }
                        # 対象サブタスクが全て既にマージ済み（再選出）だった場合は
                        # レビューする新規差分が無いため、静かに成功として扱う。
                        return {"status": "success", "merged": merged_tasks}

                    if self.config.parent_issue_number:
                        github.add_comment(
                            self.config.parent_issue_number,
                            f"🎉 すべての完了タスク ({', '.join(merged_tasks)}) の仮マージCIが正常に通過しました。\n"
                            f"仮マージブランチ `{self.config.temp_branch}` がリモートにプッシュされました。人手での最終マージが可能です。",
                        )
                return {"status": "success", "merged": merged_tasks}

            return {
                "status": "partial_success" if merged_tasks else "failure",
                "merged": merged_tasks,
                "failed": failed_tasks,
            }
        finally:
            if temp_worktree_path:
                try:
                    subprocess.run(
                        [
                            "git",
                            "worktree",
                            "remove",
                            "--force",
                            str(temp_worktree_path),
                        ],
                        cwd=str(Path(".")),
                        capture_output=True,
                        check=True,
                    )
                except Exception:
                    pass

    def _resolve_open_prs_for_merge(
        self, sorted_done_tasks: list[Task], merged_tasks: list[str]
    ) -> list[tuple[str, int, int]]:
        """#186: `merged_tasks`のうち、まだmainへ未マージ（openなPRが存在する）
        サブタスクだけを (subtask_id, issue_number, pr_number) のタプルとして、
        `merged_tasks`の依存順を保ったまま返す。

        `status:done`はdependency解決のためcloseされたIssueにも意図的に残る
        （#236）ため、`_get_sorted_done_tasks`は既にmainへマージ済みの
        サブタスクを毎サイクル再選出しうる。それらはopenなPRを持たないため、
        ここで黙って除外される（再マージや意味的レビューの対象外）。
        """
        open_pr_numbers_by_branch = {
            pr.head_ref: pr.number for pr in github.list_open_prs()
        }
        task_by_subtask = {
            task.subtask_id: task for task in sorted_done_tasks if task.subtask_id
        }
        resolved: list[tuple[str, int, int]] = []
        for subtask_id in merged_tasks:
            task = task_by_subtask.get(subtask_id)
            if task is None:
                continue
            branch_name = f"claude/issue-{task.issue_number}-{subtask_id}"
            pr_number = open_pr_numbers_by_branch.get(branch_name)
            if pr_number is None:
                continue
            resolved.append((subtask_id, task.issue_number, pr_number))
        return resolved

    def _get_sorted_done_tasks(self) -> list[Task]:
        done_issues = github.list_issues_by_label("status:done", state="all")
        if not done_issues:
            return []

        all_issues = []
        for label in [
            "status:queued",
            "status:in-progress",
            "status:blocked",
            "status:external-lock",
            "status:done",
        ]:
            state = "all" if label == "status:done" else "open"
            all_issues.extend(github.list_issues_by_label(label, state=state))

        seen_numbers = set()
        unique_issues = []
        for issue in all_issues:
            if issue.number not in seen_numbers:
                seen_numbers.add(issue.number)
                unique_issues.append(issue)

        tasks = [parse_task_from_issue(issue) for issue in unique_issues]
        subtasks = [
            SubTask(
                id=task.subtask_id,
                description="",
                footprint=task.footprint,
                symbols=task.symbols,
                depends_on=task.depends_on,
                risk=task.risk,
                risk_reasons=(),
            )
            for task in tasks
            if task.subtask_id
        ]

        try:
            dag = build_dag(subtasks)
            topological_order = dag.topological_order
        except Exception as e:
            print(f"Warning: Failed to build DAG: {e}", file=sys.stderr)
            topological_order = [t.id for t in subtasks]

        done_tasks = [parse_task_from_issue(issue) for issue in done_issues]
        done_task_map = {t.subtask_id: t for t in done_tasks if t.subtask_id}

        sorted_done_tasks = []
        for subtask_id in topological_order:
            if subtask_id in done_task_map:
                sorted_done_tasks.append(done_task_map[subtask_id])

        for t in done_tasks:
            if t.subtask_id and t.subtask_id not in [
                x.subtask_id for x in sorted_done_tasks
            ]:
                sorted_done_tasks.append(t)

        return sorted_done_tasks

    def _create_temp_branch(self) -> bool:
        if not self.config.apply:
            return True
        try:
            subprocess.run(
                [
                    "git",
                    "checkout",
                    "-B",
                    self.config.temp_branch,
                    self.config.base_branch,
                ],
                cwd=str(self.config.repository_root),
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _merge_and_test_tasks(
        self, sorted_done_tasks: list[Task]
    ) -> tuple[list[str], list[str]]:
        merged_tasks = []
        failed_tasks = []

        for task in sorted_done_tasks:
            branch_name = (
                f"claude/issue-{task.issue_number}-{task.subtask_id or 'task'}"
            )

            if self.config.apply:
                # actions/checkout のデフォルト（単一ブランチの浅いclone）では
                # `origin/{branch_name}` のremote-trackingブランチが存在しないため、
                # refspecを明示してfetchしないと後続のmergeが常に
                # 「not something we can merge」で失敗する（内容衝突ではない）。
                try:
                    subprocess.run(
                        [
                            "git",
                            "fetch",
                            "origin",
                            f"{branch_name}:refs/remotes/origin/{branch_name}",
                        ],
                        cwd=str(self.config.repository_root),
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    self._handle_failure(
                        task, f"Failed to fetch branch: {e.stderr.decode()}"
                    )
                    failed_tasks.append(task.subtask_id)
                    continue

                try:
                    subprocess.run(
                        [
                            "git",
                            "merge",
                            "--no-ff",
                            "-m",
                            f"Temp merge {branch_name}",
                            f"origin/{branch_name}",
                        ],
                        cwd=str(self.config.repository_root),
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    self._abort_merge()
                    self._handle_failure(task, f"Merge conflict: {e.stderr.decode()}")
                    failed_tasks.append(task.subtask_id)
                    continue

                ci_success = self._run_ci_with_flaky_check()
                if not ci_success:
                    subprocess.run(
                        ["git", "reset", "--hard", "HEAD~1"],
                        cwd=str(self.config.repository_root),
                        check=True,
                        capture_output=True,
                    )
                    self._handle_failure(task, "CI verification failed")
                    failed_tasks.append(task.subtask_id)
                    continue

            merged_tasks.append(task.subtask_id)

        return merged_tasks, failed_tasks

    def _abort_merge(self) -> None:
        # マージ失敗時にMERGE_HEADを残したままにすると、後続タスクのマージが
        # 「進行中の未完了マージがある」ために巻き添えで失敗してしまうため、
        # 一時ブランチの直前の状態へ確実に戻す。
        try:
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=str(self.config.repository_root),
                capture_output=True,
            )
        except (subprocess.CalledProcessError, OSError):
            pass

    def _run_ci_with_flaky_check(self) -> bool:
        ci_cmd = self.config.ci_command or ["./scripts/local-ci.sh"]
        for _ in range(1 + self.config.max_flaky_retries):
            try:
                subprocess.run(
                    ci_cmd,
                    cwd=str(self.config.repository_root),
                    check=True,
                    capture_output=True,
                )
                return True
            except subprocess.CalledProcessError:
                pass

        return False

    def _handle_failure(self, task: Task, reason: str):
        if self.config.apply:
            github.remove_label(task.issue_number, "status:done")
            github.add_label(task.issue_number, "status:queued")
            github.add_comment(
                task.issue_number,
                f"仮マージCIでエラーが検出されたため、マージを取り消し差し戻しました。\n"
                f"理由: {reason}\n"
                f"自動修復エージェントの再起動を待ちます。",
            )
