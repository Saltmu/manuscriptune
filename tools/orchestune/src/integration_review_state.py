"""#186: 統合コーディネーターの意味的レビュー結果を、次回以降のディスパッチ
サイクルで検知してPRマージを実行できるよう永続化する。`dispatch_state.py`と
同じJSONベースの永続化パターンに倣う。

レビューはClaude Codeクラウドルーチンを非同期fireするため、Python側で結果を
同期的に受け取れない。そのため「どのサブタスクPRを、どの順序でマージ対象と
したか」をここに記録し、後続サイクルで親Issueのラベル
（`semantic-review:passed`/`semantic-review:failed`）をポーリングして
Python側が決定論的にマージを実行する。
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PendingSubtaskMerge:
    subtask_id: str
    issue_number: int
    pr_number: int


@dataclass
class PendingSemanticReview:
    parent_issue_number: int
    dispatched_at: float
    subtask_prs: tuple[PendingSubtaskMerge, ...]
    session_external_id: str | None = None
    session_external_url: str | None = None


@dataclass
class IntegrationReviewState:
    pending: list[PendingSemanticReview] = field(default_factory=list)


def load_integration_review_state(path: str | Path) -> IntegrationReviewState:
    path = Path(path)
    if not path.exists():
        return IntegrationReviewState()
    data = json.loads(path.read_text(encoding="utf-8"))
    pending = [
        PendingSemanticReview(
            parent_issue_number=entry["parent_issue_number"],
            dispatched_at=entry["dispatched_at"],
            subtask_prs=tuple(
                PendingSubtaskMerge(
                    subtask_id=item["subtask_id"],
                    issue_number=item["issue_number"],
                    pr_number=item["pr_number"],
                )
                for item in entry.get("subtask_prs", [])
            ),
            session_external_id=entry.get("session_external_id"),
            session_external_url=entry.get("session_external_url"),
        )
        for entry in data.get("pending", [])
    ]
    return IntegrationReviewState(pending=pending)


def save_integration_review_state(
    state: IntegrationReviewState, path: str | Path
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pending": [
            {
                "parent_issue_number": entry.parent_issue_number,
                "dispatched_at": entry.dispatched_at,
                "subtask_prs": [dataclasses.asdict(item) for item in entry.subtask_prs],
                "session_external_id": entry.session_external_id,
                "session_external_url": entry.session_external_url,
            }
            for entry in state.pending
        ]
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
