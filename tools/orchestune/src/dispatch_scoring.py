"""Issueからのタスク定義パースと、ディスパッチ優先度の算出・選出ロジック。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime

import yaml

from src.dispatch_state import RunState
from src.github import IssueRecord

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
