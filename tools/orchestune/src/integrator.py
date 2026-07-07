from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src import github
from src.dag import SubTask, build_dag
from src.dispatcher import Task, parse_task_from_issue


@dataclass
class IntegratorConfig:
    repository_root: Path = Path(".")
    base_branch: str = "origin/main"
    temp_branch: str = "integration/temp-main"
    ci_command: list[str] | None = None
    max_flaky_retries: int = 2
    parent_issue_number: int | None = None
    apply: bool = False


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

    def _get_sorted_done_tasks(self) -> list[Task]:
        done_issues = github.list_issues_by_label("status:done")
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
            all_issues.extend(github.list_issues_by_label(label))

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
