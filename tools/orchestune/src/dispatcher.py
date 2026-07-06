from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import re
import subprocess
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

from src import github
from src.dag import FootprintConflict, SubTask, recompute_dag_for_footprint_change
from src.dispatch_targets import (
    DispatchHandle,
    DispatchTarget,
    LocalProcessDispatchTarget,
    build_dispatch_target,
    default_dry_run_command_builder,
)
from src.github import IssueRecord, PrRecord, _validate_ref_name

__all__ = [
    "DispatchHandle",
    "DispatchTarget",
    "LocalProcessDispatchTarget",
    "build_dispatch_target",
    "default_dry_run_command_builder",
]

BASE_PRIORITY = {"low": 1.0, "medium": 2.0, "high": 3.0}
TIME_BONUS_WEIGHT = 0.5
PROGRESS_BONUS = 1.0

_FOOTPRINT_BLOCK_PATTERN = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class Task:
    issue_number: int
    subtask_id: str
    footprint: tuple[str, ...]
    symbols: tuple[str, ...]
    risk: bool
    priority: str
    progress_partial: bool
    status_labels: tuple[str, ...]
    created_at: str
    depends_on: tuple[str, ...] = ()
    yaml_error: bool = False


def parse_task_from_issue(issue: IssueRecord) -> Task:
    subtask_id = ""
    footprint: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    yaml_error = False

    match = _FOOTPRINT_BLOCK_PATTERN.search(issue.body)
    if match:
        try:
            data = yaml.safe_load(match.group(1))
            if isinstance(data, dict):
                subtask_id = str(data.get("subtask_id", ""))
                footprint = tuple(str(f) for f in (data.get("footprint") or []))
                symbols = tuple(str(s) for s in (data.get("symbols") or []))
                depends_on = tuple(str(d) for d in (data.get("depends_on") or []))
        except yaml.YAMLError as e:
            import sys

            print(
                f"Warning: Failed to parse YAML from issue #{issue.number}: {e}",
                file=sys.stderr,
            )
            yaml_error = True

    priority = "medium"
    risk = False
    progress_partial = False
    for label in issue.labels:
        if label.startswith("priority:"):
            priority = label.split(":", 1)[1]
        elif label == "risk:flagged":
            risk = True
        elif label == "progress:partial":
            progress_partial = True

    return Task(
        issue_number=issue.number,
        subtask_id=subtask_id,
        footprint=footprint,
        symbols=symbols,
        risk=risk,
        priority=priority,
        progress_partial=progress_partial,
        status_labels=tuple(issue.labels),
        created_at=issue.created_at,
        depends_on=depends_on,
        yaml_error=yaml_error,
    )


@dataclass
class ActiveWorktree:
    issue_number: int
    branch: str
    worktree_path: str
    pid: int | None
    started_at: float
    declared_footprint: tuple[str, ...]
    recompute_count: int = 0
    forced_serial: bool = False
    external_id: str | None = None
    external_url: str | None = None


@dataclass
class RunState:
    active_worktrees: dict[str, ActiveWorktree] = field(default_factory=dict)
    launch_history: list[float] = field(default_factory=list)


def load_run_state(path: str | Path) -> RunState:
    path = Path(path)
    if not path.exists():
        return RunState(active_worktrees={}, launch_history=[])
    data = json.loads(path.read_text(encoding="utf-8"))
    active_worktrees = {
        key: ActiveWorktree(
            issue_number=value["issue_number"],
            branch=value["branch"],
            worktree_path=value["worktree_path"],
            pid=value["pid"],
            started_at=value["started_at"],
            declared_footprint=tuple(value["declared_footprint"]),
            recompute_count=value.get("recompute_count", 0),
            forced_serial=value.get("forced_serial", False),
            external_id=value.get("external_id"),
            external_url=value.get("external_url"),
        )
        for key, value in data.get("active_worktrees", {}).items()
    }
    return RunState(
        active_worktrees=active_worktrees,
        launch_history=list(data.get("launch_history", [])),
    )


def save_run_state(state: RunState, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "active_worktrees": {
            key: dataclasses.asdict(value)
            for key, value in state.active_worktrees.items()
        },
        "launch_history": state.launch_history,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def quota_available(
    run_state: RunState,
    now: float,
    max_concurrent: int,
    max_launches_per_window: int,
    window_seconds: int,
) -> int:
    concurrent_remaining = max(0, max_concurrent - len(run_state.active_worktrees))
    recent_launches = [t for t in run_state.launch_history if now - t < window_seconds]
    rate_remaining = max(0, max_launches_per_window - len(recent_launches))
    return min(concurrent_remaining, rate_remaining)


def _wait_seconds(task: Task, now: float) -> float:
    created = datetime.fromisoformat(task.created_at)
    return max(0.0, now - created.timestamp())


def compute_priority_score(
    task: Task, all_candidate_tasks: list[Task], now: float
) -> float:
    base_priority = BASE_PRIORITY[task.priority]
    waits = [_wait_seconds(t, now) for t in all_candidate_tasks]
    avg_wait = sum(waits) / len(waits) if waits else 0.0

    time_bonus = 0.0
    if avg_wait > 0:
        wait = _wait_seconds(task, now)
        time_bonus = max(0.0, (wait / avg_wait) - 1.0) * TIME_BONUS_WEIGHT

    progress_factor = PROGRESS_BONUS if task.progress_partial else 0.0
    return base_priority * (1.0 + time_bonus) + progress_factor


def select_next_tasks(
    candidate_tasks: list[Task],
    run_state: RunState,
    now: float,
    max_concurrent: int,
    max_launches_per_window: int,
    window_seconds: int,
) -> list[Task]:
    active_issue_numbers = {int(k) for k in run_state.active_worktrees}
    eligible = [
        t
        for t in candidate_tasks
        if not t.risk
        and not t.yaml_error
        and "status:external-lock" not in t.status_labels
        and t.issue_number not in active_issue_numbers
    ]
    slots = quota_available(
        run_state, now, max_concurrent, max_launches_per_window, window_seconds
    )
    scored = sorted(
        eligible,
        key=lambda t: (-compute_priority_score(t, eligible, now), t.issue_number),
    )
    return scored[:slots]


@dataclass
class ExternalLockScanResult:
    to_lock: list[Task]
    to_unlock: list[Task]


def scan_external_locks(
    queued_tasks: list[Task],
    remote_branches: Iterable[tuple[str, tuple[str, ...]]],
    prs: list[PrRecord],
    active_branches: Iterable[str],
) -> ExternalLockScanResult:
    active_set = set(active_branches)
    external_footprints: list[set[str]] = []

    for pr in prs:
        if pr.head_ref in active_set:
            continue
        external_footprints.append(set(pr.changed_files))

    for branch, changed_files in remote_branches:
        if branch in active_set:
            continue
        external_footprints.append(set(changed_files))

    to_lock: list[Task] = []
    to_unlock: list[Task] = []
    for task in queued_tasks:
        overlaps = any(
            set(task.footprint) & footprint for footprint in external_footprints
        )
        currently_locked = "status:external-lock" in task.status_labels
        if overlaps and not currently_locked:
            to_lock.append(task)
        elif not overlaps and currently_locked:
            to_unlock.append(task)

    return ExternalLockScanResult(to_lock=to_lock, to_unlock=to_unlock)


def check_footprint_deviation(
    worktree_path: str | Path,
    declared_footprint: tuple[str, ...],
    base: str = "origin/main",
    min_changed_lines: int = 0,
) -> list[str]:
    """宣言footprint外のファイル変更を検知する。

    #200: ライブロック（チャーン）防止のため、`min_changed_lines`以下の
    変更行数（追加+削除）しかない微小な逸脱はバッファとして無視する。
    バイナリファイル（`git diff --numstat`が行数の代わりに`-`を返す）は
    行数で測れないため、バッファに関わらず常に逸脱として報告する。
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree_path), "diff", "--numstat", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return []

    declared = set(declared_footprint)
    deviated: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_str, deleted_str, path = parts
        if path in declared:
            continue
        if added_str == "-" or deleted_str == "-":
            changed_lines = min_changed_lines + 1
        else:
            changed_lines = int(added_str) + int(deleted_str)
        if changed_lines > min_changed_lines:
            deviated.append(path)
    return deviated


def notify_recompute(
    conflict: FootprintConflict,
    work_summary: str,
    parent_issue_number: int | None,
    apply: bool,
    issue_number_by_subtask_id: dict[str, int],
) -> list[str]:
    detail = (
        "footprint逸脱によるDAG再計算が発生しました。\n\n"
        f"- 発覚したサブタスク: {conflict.subtask_id}\n"
        f"- 競合相手のサブタスク: {conflict.other_subtask_id}\n"
        f"- 結合度スコア: {conflict.similarity:.3f}\n"
        f"- ブロックされるサブタスク: {conflict.blocked_subtask_id}\n"
        f"- 発覚時点までの作業内容: {work_summary}\n"
    )
    bodies = [detail, detail]

    subtask_issue = issue_number_by_subtask_id.get(conflict.subtask_id)
    other_issue = issue_number_by_subtask_id.get(conflict.other_subtask_id)
    blocked_issue = issue_number_by_subtask_id.get(conflict.blocked_subtask_id)

    if parent_issue_number is not None:
        bodies.append(
            f"[自動記録] サブタスク {conflict.subtask_id} と {conflict.other_subtask_id} の"
            f"間でfootprint逸脱によるDAG再計算が発生しました。\n\n{detail}"
        )

    if apply:
        if subtask_issue is not None:
            github.add_comment(subtask_issue, detail)
        if other_issue is not None:
            github.add_comment(other_issue, detail)
        if parent_issue_number is not None:
            github.add_comment(parent_issue_number, bodies[-1])
        if blocked_issue is not None:
            github.add_label(blocked_issue, "status:blocked-recompute")

    return bodies


def notify_force_serial(
    subtask_id: str,
    issue_number: int,
    parent_issue_number: int | None,
    retry_count: int,
    apply: bool,
) -> str:
    """#200: DAG再計算のリトライ上限超過を親Issueへ通知し、強制直列化を告知する。"""
    body = (
        "footprint逸脱によるDAG再計算のリトライ上限に達しました。\n\n"
        f"- サブタスク: {subtask_id}\n"
        f"- 対象Issue: #{issue_number}\n"
        f"- 再計算試行回数: {retry_count}\n\n"
        "ライブロック（チャーン）を防ぐため、このサブタスクを単独で直列実行する"
        "フォールバックに切り替えます。新規タスクのdispatchは、このサブタスクが"
        "完了するまで一時停止します。\n"
    )
    if apply and parent_issue_number is not None:
        github.add_comment(parent_issue_number, body)
    return body


@dataclass
class LaunchResult:
    issue_number: int
    branch: str
    worktree_path: str
    pid: int | None
    launched: bool
    error_message: str | None = None
    external_id: str | None = None
    external_url: str | None = None


def create_worktree_and_launch(
    task: Task,
    branch_name: str,
    worktree_root: str | Path,
    dispatch_target: DispatchTarget,
    apply: bool,
) -> LaunchResult:
    _validate_ref_name(branch_name)
    worktree_root = Path(worktree_root)
    slug = branch_name.replace("/", "-")
    worktree_path = worktree_root / slug

    pid: int | None = None
    external_id: str | None = None
    external_url: str | None = None
    launched = False
    error_message: str | None = None

    if apply:
        try:
            # 1. 無効なworktreeの整理
            subprocess.run(["git", "worktree", "prune"], capture_output=True, text=True)

            # 2. すでにディレクトリが存在する場合のクリーンアップ
            if worktree_path.exists():
                import shutil

                try:
                    shutil.rmtree(worktree_path)
                except Exception:
                    pass

            worktree_root.mkdir(parents=True, exist_ok=True)

            # 3. ブランチがすでに存在する場合は -B で強制リセットする
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-B", branch_name],
                capture_output=True,
                text=True,
                check=True,
            )
            handle = dispatch_target.launch(task, branch_name, worktree_path)
            pid = handle.pid
            external_id = handle.external_id
            external_url = handle.external_url
            launched = True
        except (subprocess.CalledProcessError, OSError) as e:
            import sys

            error_details = ""
            if isinstance(e, subprocess.CalledProcessError):
                error_details = f" (stderr: {e.stderr.strip() if e.stderr else ''})"
            print(
                f"Error: Failed to create worktree or launch for issue #{task.issue_number}: {e}{error_details}",
                file=sys.stderr,
            )
            error_message = f"{e}{error_details}"

    return LaunchResult(
        issue_number=task.issue_number,
        branch=branch_name,
        worktree_path=str(worktree_path),
        pid=pid,
        launched=launched,
        error_message=error_message,
        external_id=external_id,
        external_url=external_url,
    )


def is_process_alive(pid: int | None) -> bool:
    """#193: 記録済みpidのプロセス生存確認によるタスク完了判定。

    シグナル送信権限がない場合（別ユーザー所有のPID再利用等）は、
    安全側に倒し「生存している」とみなす。
    """
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def worktree_has_uncommitted_changes(worktree_path: str | Path) -> bool:
    """#193: worktree削除前の未コミット変更確認。

    `git status`自体が失敗する場合（worktreeが既に手動削除済み等）は、
    クオータ解放を優先し安全側でクリーン（変更なし）として扱う。
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return False
    return bool(result.stdout.strip())


def remove_worktree(worktree_path: str | Path) -> None:
    """#193: 完了したworktreeを撤去する。既に手動削除済み等の失敗は無視する
    （run_stateからのクオータ解放を妨げないことを優先する）。"""
    try:
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        pass


@dataclass
class DispatcherConfig:
    max_concurrent: int = 2
    max_launches_per_window: int = 1
    window_seconds: int = 3600
    run_state_path: Path = Path("run_state.json")
    worktree_root: Path = Path("worktrees")
    log_dir: Path = Path("logs")
    parent_issue_number: int | None = None
    apply: bool = False
    dispatch_target: DispatchTarget | None = None
    deviation_buffer_lines: int = 5
    max_recompute_retries: int = 2

    def __post_init__(self) -> None:
        if self.dispatch_target is None:
            self.dispatch_target = LocalProcessDispatchTarget(log_dir=self.log_dir)


@dataclass
class CycleReport:
    selected: list[Task]
    quota_slots_available: int
    lock_changes: dict[str, list[Task]]
    deviation_events: list[dict]
    completion_events: list[dict]
    promotion_events: list[dict]
    applied: bool


def _build_subtasks_for_recompute(
    tasks_by_issue: dict[int, Task],
) -> dict[str, SubTask]:
    return {
        task.subtask_id: SubTask(
            id=task.subtask_id,
            description="",
            footprint=task.footprint,
            symbols=task.symbols,
            depends_on=(),
            risk=task.risk,
            risk_reasons=(),
        )
        for task in tasks_by_issue.values()
        if task.subtask_id
    }


def _handle_footprint_deviation(
    active: ActiveWorktree,
    deviated: list[str],
    tasks_by_issue: dict[int, Task],
    issue_number_by_subtask_id: dict[str, int],
    config: DispatcherConfig,
) -> dict:
    """#192/#200: 1つのactive worktreeのfootprint逸脱を処理し、イベントを返す。

    既に強制直列化済みなら何もしない（チャーン防止）。リトライ上限超過なら
    強制直列化にフォールバックし、それ以外はDAG再計算・通知を実行する。
    """
    event: dict = {"issue_number": active.issue_number, "deviated_files": deviated}

    if active.forced_serial:
        event["action"] = "already_forced_serial"
        return event

    active_task = tasks_by_issue.get(active.issue_number)
    if active_task is None or not active_task.subtask_id:
        event["action"] = "skipped_unknown_subtask"
        return event

    if active.recompute_count >= config.max_recompute_retries:
        notify_force_serial(
            active_task.subtask_id,
            active.issue_number,
            config.parent_issue_number,
            active.recompute_count,
            apply=config.apply,
        )
        event["action"] = "forced_serial"
        event["recompute_count"] = active.recompute_count
        if config.apply:
            active.forced_serial = True
            github.add_label(active.issue_number, "status:force-serial")
        return event

    merged_footprint = tuple(dict.fromkeys([*active.declared_footprint, *deviated]))
    _, conflicts = recompute_dag_for_footprint_change(
        _build_subtasks_for_recompute(tasks_by_issue),
        active_task.subtask_id,
        updated_footprint=merged_footprint,
    )

    for conflict in conflicts:
        notify_recompute(
            conflict,
            work_summary=f"{', '.join(deviated)} への逸脱を検知",
            parent_issue_number=config.parent_issue_number,
            apply=config.apply,
            issue_number_by_subtask_id=issue_number_by_subtask_id,
        )

    event["action"] = "recomputed"
    event["conflicts"] = [dataclasses.asdict(c) for c in conflicts]
    if config.apply:
        active.recompute_count += 1
    return event


def _finalize_completed_worktree(
    active: ActiveWorktree,
    active_task: Task | None,
    config: DispatcherConfig,
) -> dict:
    """#193: プロセス終了を検知したactive worktreeの完了後処理。

    未コミットの変更が残っている場合は、削除・ラベル遷移を行わず人間の
    確認を待つ（安全側に倒し、作業内容の消失を防ぐ）。
    """
    event: dict = {
        "issue_number": active.issue_number,
        "worktree_path": active.worktree_path,
    }

    if worktree_has_uncommitted_changes(active.worktree_path):
        event["action"] = "completion_skipped_dirty_worktree"
        return event

    if config.apply:
        remove_worktree(active.worktree_path)
        github.remove_label(active.issue_number, "status:in-progress")
        github.add_label(active.issue_number, "status:done")

    event["action"] = "completed"
    event["subtask_id"] = active_task.subtask_id if active_task else ""
    return event


def _is_worktree_complete(active: ActiveWorktree, config: DispatcherConfig) -> bool:
    """#215: `external_id`が設定されている（ローカルpid以外でディスパッチされた）
    active worktreeは、設定されたdispatch_targetの`is_complete`に完了判定を委譲する。
    それ以外（従来通りのローカルsubprocess起動）は`is_process_alive`ベースのまま。"""
    if active.external_id is not None:
        handle = DispatchHandle(
            pid=active.pid,
            external_id=active.external_id,
            external_url=active.external_url,
            branch_name=active.branch,
        )
        assert config.dispatch_target is not None
        return config.dispatch_target.is_complete(handle)
    return not is_process_alive(active.pid)


def _process_active_worktrees(
    run_state: RunState,
    tasks_by_issue: dict[int, Task],
    issue_number_by_subtask_id: dict[str, int],
    config: DispatcherConfig,
) -> tuple[list[dict], list[dict], bool, set[str]]:
    """#192/#193/#200: active worktreeごとの完了検知・footprint逸脱処理。

    完了と判定したエントリは（apply時）run_state.active_worktreesから
    除去してクオータを解放し、以後のfootprint逸脱チェックはスキップする。
    """
    completion_events: list[dict] = []
    deviation_events: list[dict] = []
    any_forced_serial = False
    completed_subtask_ids: set[str] = set()

    for key, active in list(run_state.active_worktrees.items()):
        if active.forced_serial:
            any_forced_serial = True

        active_task = tasks_by_issue.get(active.issue_number)

        if _is_worktree_complete(active, config):
            completion_event = _finalize_completed_worktree(active, active_task, config)
            completion_events.append(completion_event)
            if completion_event["action"] == "completed":
                if active_task is not None and active_task.subtask_id:
                    completed_subtask_ids.add(active_task.subtask_id)
                if config.apply:
                    del run_state.active_worktrees[key]
                continue

        deviated = check_footprint_deviation(
            active.worktree_path,
            active.declared_footprint,
            min_changed_lines=config.deviation_buffer_lines,
        )
        if not deviated:
            continue

        event = _handle_footprint_deviation(
            active, deviated, tasks_by_issue, issue_number_by_subtask_id, config
        )
        if event["action"] in ("forced_serial", "already_forced_serial"):
            any_forced_serial = True
        deviation_events.append(event)

    return completion_events, deviation_events, any_forced_serial, completed_subtask_ids


def _promote_blocked_tasks(
    blocked_issues: list[IssueRecord],
    done_issues: list[IssueRecord],
    completed_subtask_ids: set[str],
    config: DispatcherConfig,
) -> list[dict]:
    """#193: 依存先が全て解決したstatus:blockedタスクをstatus:queuedへ昇格する。"""
    done_subtask_ids = {
        task.subtask_id
        for task in (parse_task_from_issue(issue) for issue in done_issues)
        if task.subtask_id
    } | completed_subtask_ids

    events: list[dict] = []
    for issue in blocked_issues:
        task = parse_task_from_issue(issue)
        if not task.depends_on:
            continue
        if not all(dep in done_subtask_ids for dep in task.depends_on):
            continue
        if config.apply:
            github.remove_label(task.issue_number, "status:blocked")
            github.add_label(task.issue_number, "status:queued")
        events.append(
            {"issue_number": task.issue_number, "subtask_id": task.subtask_id}
        )
    return events


def _strip_remote_prefix(branch: str, remote: str = "origin") -> str:
    """#194: `git branch -r`由来のリモート名プレフィックスを剥がし、
    PRのheadRefName・ディスパッチャ自身のブランチ名と同じ名前空間に正規化する。"""
    prefix = f"{remote}/"
    return branch[len(prefix) :] if branch.startswith(prefix) else branch


@contextlib.contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return

    lock_fd = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise RuntimeError(
            f"Another instance is already running (locked on {lock_path})"
        ) from None
    except Exception as e:
        import sys

        print(f"Warning: Failed to acquire lock: {e}", file=sys.stderr)
        yield
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            lock_fd.close()


def run_dispatch_cycle(config: DispatcherConfig) -> CycleReport:
    lock_path = Path(config.run_state_path).with_suffix(".lock")
    with file_lock(lock_path):
        run_state = load_run_state(config.run_state_path)
        now = time.time()

        queued_issues = github.list_issues_by_label("status:queued")
        locked_issues = github.list_issues_by_label("status:external-lock")
        in_progress_issues = github.list_issues_by_label("status:in-progress")
        blocked_issues = github.list_issues_by_label("status:blocked")
        done_issues = github.list_issues_by_label("status:done")
        tasks_by_issue = {
            issue.number: parse_task_from_issue(issue)
            for issue in [
                *queued_issues,
                *locked_issues,
                *in_progress_issues,
                *blocked_issues,
            ]
        }
        issue_number_by_subtask_id = {
            task.subtask_id: task.issue_number
            for task in tasks_by_issue.values()
            if task.subtask_id
        }

        (
            completion_events,
            deviation_events,
            any_forced_serial,
            completed_subtask_ids,
        ) = _process_active_worktrees(
            run_state, tasks_by_issue, issue_number_by_subtask_id, config
        )

        promotion_events = _promote_blocked_tasks(
            blocked_issues, done_issues, completed_subtask_ids, config
        )

        remote_branch_names = github.list_remote_branches()
        prs = github.list_open_prs()
        active_branches = [aw.branch for aw in run_state.active_worktrees.values()]
        pr_head_refs = {pr.head_ref for pr in prs}
        bare_branches = [
            b
            for b in remote_branch_names
            if _strip_remote_prefix(b) not in pr_head_refs
            and _strip_remote_prefix(b) not in active_branches
        ]
        remote_branch_footprints = [
            (_strip_remote_prefix(branch), tuple(github.branch_changed_files(branch)))
            for branch in bare_branches
        ]

        all_tasks = list(tasks_by_issue.values())
        lock_result = scan_external_locks(
            all_tasks, remote_branch_footprints, prs, active_branches
        )

        if config.apply:
            for task in lock_result.to_lock:
                github.add_label(task.issue_number, "status:external-lock")
            for task in lock_result.to_unlock:
                github.remove_label(task.issue_number, "status:external-lock")
                github.add_label(task.issue_number, "status:queued")

        newly_locked = {t.issue_number for t in lock_result.to_lock}
        candidate_tasks = [
            tasks_by_issue[issue.number]
            for issue in queued_issues
            if issue.number not in newly_locked
        ]

        if any_forced_serial:
            # #200: リトライ上限を超えたサブタスクを直列実行させるため、
            # 完了するまで新規タスクのdispatchを凍結する。
            quota_slots = 0
            selected: list[Task] = []
        else:
            quota_slots = quota_available(
                run_state,
                now,
                config.max_concurrent,
                config.max_launches_per_window,
                config.window_seconds,
            )
            selected = select_next_tasks(
                candidate_tasks,
                run_state,
                now,
                config.max_concurrent,
                config.max_launches_per_window,
                config.window_seconds,
            )

        if config.apply:
            # YAMLパースエラーになっているタスクをブロックする
            for task in candidate_tasks:
                if task.yaml_error:
                    github.remove_label(task.issue_number, "status:queued")
                    github.add_label(task.issue_number, "status:blocked")
                    github.add_comment(
                        task.issue_number,
                        "YAMLのパースに失敗したため、タスクをブロックしました。フォーマットを確認してください。",
                    )

            actually_selected = []
            for task in selected:
                branch_name = (
                    f"claude/issue-{task.issue_number}-{task.subtask_id or 'task'}"
                )
                assert config.dispatch_target is not None
                launch = create_worktree_and_launch(
                    task,
                    branch_name,
                    config.worktree_root,
                    config.dispatch_target,
                    apply=True,
                )
                if not launch.launched:
                    github.remove_label(task.issue_number, "status:queued")
                    github.add_label(task.issue_number, "status:blocked")
                    github.add_comment(
                        task.issue_number,
                        f"Git worktreeの作成またはエージェントの起動に失敗しました。\n"
                        f"エラー内容:\n```\n{launch.error_message}\n```",
                    )
                    continue

                github.remove_label(task.issue_number, "status:queued")
                github.add_label(task.issue_number, "status:in-progress")
                run_state.active_worktrees[str(task.issue_number)] = ActiveWorktree(
                    issue_number=task.issue_number,
                    branch=branch_name,
                    worktree_path=launch.worktree_path,
                    pid=launch.pid,
                    started_at=now,
                    declared_footprint=task.footprint,
                    external_id=launch.external_id,
                    external_url=launch.external_url,
                )
                run_state.launch_history.append(now)
                actually_selected.append(task)
            selected = actually_selected
            save_run_state(run_state, config.run_state_path)

        return CycleReport(
            selected=selected,
            quota_slots_available=quota_slots,
            lock_changes={
                "to_lock": lock_result.to_lock,
                "to_unlock": lock_result.to_unlock,
            },
            deviation_events=deviation_events,
            completion_events=completion_events,
            promotion_events=promotion_events,
            applied=config.apply,
        )


def _report_to_dict(report: CycleReport) -> dict:
    return {
        "applied": report.applied,
        "quota_slots_available": report.quota_slots_available,
        "selected": [dataclasses.asdict(t) for t in report.selected],
        "lock_changes": {
            "to_lock": [dataclasses.asdict(t) for t in report.lock_changes["to_lock"]],
            "to_unlock": [
                dataclasses.asdict(t) for t in report.lock_changes["to_unlock"]
            ],
        },
        "deviation_events": report.deviation_events,
        "completion_events": report.completion_events,
        "promotion_events": report.promotion_events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="スケジューラ駆動ディスパッチャー: 1サイクル分の選出・dispatchを実行する（既定はdry-run）"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際にラベル更新・worktree作成・エージェント起動を行う（未指定時はdry-run）",
    )
    parser.add_argument("--max-concurrent", type=int, default=2)
    parser.add_argument("--max-launches-per-window", type=int, default=1)
    parser.add_argument("--window-seconds", type=int, default=3600)
    parser.add_argument("--run-state-path", type=Path, default=Path("run_state.json"))
    parser.add_argument("--worktree-root", type=Path, default=Path("worktrees"))
    parser.add_argument("--log-dir", type=Path, default=Path("logs"))
    parser.add_argument("--parent-issue", type=int, default=None)
    parser.add_argument(
        "--deviation-buffer-lines",
        type=int,
        default=5,
        help="footprint逸脱として扱わない変更行数の許容バッファ（#200: ライブロック防止）",
    )
    parser.add_argument(
        "--max-recompute-retries",
        type=int,
        default=2,
        help="DAG再計算のリトライ上限。超過時は強制直列化にフォールバックする（#200）",
    )
    parser.add_argument(
        "--dispatch-target",
        choices=["local", "cloud-routine"],
        default="local",
        help="#215: エージェントの実ディスパッチ先。'cloud-routine'はClaude Codeクラウド"
        "ルーチンのfire APIへディスパッチする（要 --routine-id/--routine-token または"
        "ORCHESTUNE_ROUTINE_ID/ORCHESTUNE_ROUTINE_TOKEN環境変数）",
    )
    parser.add_argument(
        "--routine-id",
        default=None,
        help="#215: クラウドルーチンのID（未指定時はORCHESTUNE_ROUTINE_ID環境変数を使用）",
    )
    parser.add_argument(
        "--routine-token",
        default=None,
        help="#215: クラウドルーチンのAPIトークン（未指定時はORCHESTUNE_ROUTINE_TOKEN環境変数を使用）",
    )
    args = parser.parse_args(argv)

    config = DispatcherConfig(
        max_concurrent=args.max_concurrent,
        max_launches_per_window=args.max_launches_per_window,
        window_seconds=args.window_seconds,
        run_state_path=args.run_state_path,
        worktree_root=args.worktree_root,
        log_dir=args.log_dir,
        parent_issue_number=args.parent_issue,
        apply=args.apply,
        dispatch_target=build_dispatch_target(
            args.dispatch_target, args.routine_id, args.routine_token, args.log_dir
        ),
        deviation_buffer_lines=args.deviation_buffer_lines,
        max_recompute_retries=args.max_recompute_retries,
    )
    try:
        report = run_dispatch_cycle(config)
        print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2))
    except RuntimeError as e:
        import sys

        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
