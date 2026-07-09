"""#186: 仮マージCI通過後の最終防衛線となるLLM統合コーディネーター。

仮マージCIが全通過した「成功」状態のときのみ、dispatcherと**同一のClaude Code
汎用ルーチン**（`ORCHESTUNE_ROUTINE_ID`/`ORCHESTUNE_ROUTINE_TOKEN`）を起動して
意味的レビューを行う。起動されたClaude Codeセッションが仮マージブランチの結合diffを
検証し、DAGでは検知できない意味的バグ（同一のグローバル設定に対する競合する利用など）を
探す。

判定結果は親Issueへのラベル付与（`semantic-review:passed`/`semantic-review:failed`）で
Python側へ機械可読に伝える。**レビューセッション自身はマージを実行しない** ——
`dispatch_targets.py`のfireは非同期のfire-and-forget（`ClaudeCodeCloudRoutineDispatchTarget`
は結果を同期取得できない）ため、実際のマージは後続のディスパッチサイクルで
`process_pending_reviews()` がラベルをポーリングし、Python側が決定論的に実行する。
これにより「マージしても問題ないものは実際にマージする」という#181当初の
委任思想を、mainへの書き込みという不可逆操作をLLMの一存に委ねずに実現する。

差し戻し後の再レビューは、fireのたびに前回の指摘を記憶しない新規のClaude Code
セッションが起動されるため、判断のバイアスが自然に避けられる
（metaswarmプロジェクトの知見と整合）。
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from src import github
from src.dispatch_targets import (
    ROUTINE_ID_ENV_VAR,
    ROUTINE_TOKEN_ENV_VAR,
    ClaudeCodeCloudRoutineDispatchTarget,
    DispatchHandle,
)
from src.integration_review_state import (
    IntegrationReviewState,
    PendingSemanticReview,
    PendingSubtaskMerge,
    load_integration_review_state,
    save_integration_review_state,
)
from src.not_needed_review_state import (
    NotNeededReviewState,
    PendingNotNeededReview,
    load_not_needed_review_state,
    save_not_needed_review_state,
)

PASSED_LABEL = "semantic-review:passed"
FAILED_LABEL = "semantic-review:failed"

# #282: status:not-needed判定の独立検証結果ラベル。
NOT_NEEDED_VERIFIED_LABEL = "not-needed-review:passed"
NOT_NEEDED_REJECTED_LABEL = "not-needed-review:failed"

# #282: 対応不要判定によるクローズ時、事後の可視性確保のためメンションする、
# 本リポジトリの唯一のメンテナー。
NOT_NEEDED_ATTENTION_MENTION = "@Saltmu"


class RoutineFirer(Protocol):
    """任意テキスト指示でルーチンをfireできるオブジェクト（テスト差し替え用）。"""

    def fire_text(self, text: str) -> DispatchHandle: ...


def build_review_routine_prompt(
    temp_branch: str,
    base_branch: str,
    parent_issue_number: int | None,
    merged_subtask_ids: Sequence[str],
) -> str:
    """意味的レビューを実行させるためのルーチン指示テキストを構築する。

    再レビュー時のバイアス回避のため、過去の指摘内容は一切含めない
    （新規セッションが毎回まっさらな状態でレビューする）。
    """
    subtask_list = ", ".join(merged_subtask_ids) if merged_subtask_ids else "(不明)"
    parent_ref = f"#{parent_issue_number}" if parent_issue_number else "(親Issue不明)"
    return (
        "あなたは複数の並列実装タスクを統合した仮マージブランチの最終レビュアーです。\n"
        "各サブタスクの単体CIおよび仮マージCI（Ruff/Mypy/Pytest）は既に通過しています。\n\n"
        f"対象ブランチ: `{temp_branch}`（origin にプッシュ済み）\n"
        f"比較ベース: `{base_branch}`\n"
        f"統合対象サブタスク: {subtask_list}\n"
        f"親Issue: {parent_ref}\n\n"
        "手順:\n"
        f"1. `git fetch origin {temp_branch}` の上で "
        f"`git diff {base_branch}...origin/{temp_branch}` の結合diffを取得する。\n"
        "2. 静的解析やテストでは検知できない『意味的バグ』のみを探す。特に:\n"
        "   - 同一のグローバル設定・共有状態・定数に対する、複数タスク間の競合する変更\n"
        "   - 一方のタスクが変更した関数シグネチャ・契約に、他方が追随できていない不整合\n"
        "   - 個々には正しいが結合すると破綻するロジック（重複した副作用・二重処理等）\n"
        "3. 判定に応じて次のいずれかをGitHub上で実施する:\n"
        f"   - 問題なし → 親Issue {parent_ref} に `{PASSED_LABEL}` ラベルを付与する"
        f'（`gh issue edit <番号> --add-label "{PASSED_LABEL}"`）。\n'
        "   - 問題あり → 原因となったサブタスクのIssueについて、ラベルを "
        "`status:done` から `status:queued` へ付け替え、検出した問題の具体的な説明を"
        f"コメントする。あわせて親Issue {parent_ref} に `{FAILED_LABEL}` ラベルを付与する。\n"
        "**重要な制約**: あなたはラベル付与・コメント・（問題あり時の）ラベル付け替えのみを"
        "行ってください。PRのマージ（`gh pr merge`等）やmainブランチへの直接の書き込みは"
        "絶対に実行しないでください。実際のマージは、あなたが付与したラベルを検知した"
        "別のシステムが責任を持って行います。\n"
        "前回のレビュー内容は与えられていません。今回のdiffだけを根拠に判断してください。"
    )


def build_not_needed_review_prompt(issue_number: int, subtask_id: str) -> str:
    """#282: `status:not-needed`（対応不要）判定を独立に検証させるための
    ルーチン指示テキストを構築する。

    再レビュー時のバイアス回避のため、判定を行った側の主張以外の事前情報は
    与えず、新規セッションが自らIssue・コメント・`main`を確認して判断する。
    """
    return (
        "あなたは、別のセッションが「対応不要（既に要件を満たしている）」と"
        f"判定したGitHub Issue #{issue_number}（サブタスク: {subtask_id}）を"
        "独立に検証するレビュアーです。\n\n"
        "手順:\n"
        f"1. `gh issue view {issue_number} --comments` でIssue本文と、"
        "「対応不要」と判定した根拠のコメントを確認する。\n"
        "2. その根拠が正しいか、`main`ブランチの実際のコード・テストを確認して"
        "独立に検証する（該当コミット・ファイルが本当に存在し、要件を満たしているか）。\n"
        "3. 判定に応じて次のいずれかをGitHub上で実施する:\n"
        f"   - 根拠が妥当（本当に対応不要） → Issue #{issue_number} に "
        f"`{NOT_NEEDED_VERIFIED_LABEL}` ラベルのみを付与する"
        f'（`gh issue edit {issue_number} --add-label "{NOT_NEEDED_VERIFIED_LABEL}"`）。'
        "Issueのクローズは行わない（クローズは別のシステムが責任を持って行う）。\n"
        f"   - 根拠が不当（実際にはまだ対応が必要） → Issue #{issue_number} の"
        "ラベルを`status:not-needed`から`status:queued`へ付け替え、なぜ対応不要と"
        f"言えないのかを具体的にコメントする。あわせて`{NOT_NEEDED_REJECTED_LABEL}`"
        "ラベルを付与する。\n"
        "**重要な制約**: あなたはラベル付与・コメント・（不当時の）ラベル付け替えのみを"
        "行ってください。Issueのクローズ（`gh issue close`等）は絶対に実行しないで"
        "ください。実際のクローズは、あなたが付与したラベルを検知した別のシステムが"
        "責任を持って行います。\n"
        "前回のレビュー内容は与えられていません。今回自分で確認した内容だけを"
        "根拠に判断してください。"
    )


class IntegrationCoordinator:
    """dispatcherと同一のルーチンを起動して意味的レビューを委譲する。

    `dispatch_review()` は毎回ルーチンをfireするだけで、判定（合否ラベル付与）は
    起動されたClaude Codeセッションが担う。fireのたびに新規セッションが立つため、
    再レビュー時も前回の指摘を引き継がない。
    """

    def __init__(self, routine_firer: RoutineFirer):
        self._routine_firer = routine_firer

    def dispatch_review(
        self,
        temp_branch: str,
        base_branch: str,
        parent_issue_number: int | None,
        merged_subtask_ids: Sequence[str],
    ) -> DispatchHandle:
        prompt = build_review_routine_prompt(
            temp_branch=temp_branch,
            base_branch=base_branch,
            parent_issue_number=parent_issue_number,
            merged_subtask_ids=merged_subtask_ids,
        )
        return self._routine_firer.fire_text(prompt)

    def dispatch_not_needed_review(
        self, issue_number: int, subtask_id: str
    ) -> DispatchHandle:
        """#282: `status:not-needed`判定を独立に検証するレビューをfireする。"""
        prompt = build_not_needed_review_prompt(issue_number, subtask_id)
        return self._routine_firer.fire_text(prompt)


def build_integration_coordinator() -> IntegrationCoordinator | None:
    """環境変数のルーチン認証情報から統合コーディネーターを構築する。

    `ORCHESTUNE_ROUTINE_ID`/`ORCHESTUNE_ROUTINE_TOKEN` が揃っていなければ `None` を
    返し、呼び出し側で意味的レビューを安全にスキップさせる。dispatcher本体では、
    既に構築済みの `ClaudeCodeCloudRoutineDispatchTarget` を直接再利用する経路も使う。
    """
    routine_id = os.environ.get(ROUTINE_ID_ENV_VAR)
    routine_token = os.environ.get(ROUTINE_TOKEN_ENV_VAR)
    if not (routine_id and routine_token):
        return None
    return IntegrationCoordinator(
        ClaudeCodeCloudRoutineDispatchTarget(routine_id, routine_token)
    )


def process_pending_reviews(state_path: str | Path) -> dict:
    """#186: 保留中の意味的レビューをポーリングし、合格したものはPRを決定論的に
    マージする。レビューセッション自身はマージを実行しないため、この関数が
    「マージしても問題ないものを実際にマージする」実行主体を担う。

    - `semantic-review:passed` を検知 → 記録済みのPRを検証済み順序でマージし、
      ラベルを外して記録を消費する。個々のPRマージ失敗（既にマージ済み/コンフリクト等）
      は他のPRの処理を止めない。
    - `semantic-review:failed` を検知 → サブタスクへの差し戻しは既にレビュー
      セッション自身が行っているため、Python側はラベルを外して記録を消費するのみ。
    - どちらのラベルもまだ無ければ、記録はそのまま保持し次サイクルで再確認する。
    """
    state = load_integration_review_state(state_path)
    if not state.pending:
        return {"merged": [], "failed": [], "still_pending": 0}

    still_pending: list[PendingSemanticReview] = []
    merged_summary: list[dict] = []
    failed_summary: list[int] = []

    for entry in state.pending:
        try:
            labels = github.get_issue_labels(entry.parent_issue_number)
        except Exception as exc:  # noqa: BLE001 - GitHub障害でクラッシュさせない
            print(
                f"Warning: failed to poll labels for issue "
                f"{entry.parent_issue_number}: {exc}",
                file=sys.stderr,
            )
            still_pending.append(entry)
            continue

        if PASSED_LABEL in labels:
            merged_prs = []
            for subtask in entry.subtask_prs:
                try:
                    github.merge_pr(subtask.pr_number)
                    merged_prs.append(subtask.subtask_id)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"Warning: failed to merge PR #{subtask.pr_number} "
                        f"({subtask.subtask_id}): {exc}",
                        file=sys.stderr,
                    )
            github.remove_label(entry.parent_issue_number, PASSED_LABEL)
            github.add_comment(
                entry.parent_issue_number,
                "✅ 意味的レビュー通過を検知したため、以下のサブタスクPRを自動マージしました:\n"
                + "\n".join(f"- {subtask_id}" for subtask_id in merged_prs)
                if merged_prs
                else "✅ 意味的レビュー通過を検知しましたが、マージ対象PRはありませんでした。",
            )
            merged_summary.append(
                {
                    "parent_issue_number": entry.parent_issue_number,
                    "merged_subtasks": merged_prs,
                }
            )
        elif FAILED_LABEL in labels:
            github.remove_label(entry.parent_issue_number, FAILED_LABEL)
            failed_summary.append(entry.parent_issue_number)
        else:
            still_pending.append(entry)

    save_integration_review_state(
        IntegrationReviewState(pending=still_pending), state_path
    )
    return {
        "merged": merged_summary,
        "failed": failed_summary,
        "still_pending": len(still_pending),
    }


def record_pending_review(
    state_path: str | Path,
    parent_issue_number: int,
    subtask_prs: Sequence[tuple[str, int, int]],
    session_handle: DispatchHandle,
) -> None:
    """dispatch_review直後に呼び、後続サイクルでのポーリング対象として記録する。"""
    state = load_integration_review_state(state_path)
    state.pending.append(
        PendingSemanticReview(
            parent_issue_number=parent_issue_number,
            dispatched_at=time.time(),
            subtask_prs=tuple(
                PendingSubtaskMerge(
                    subtask_id=subtask_id,
                    issue_number=issue_number,
                    pr_number=pr_number,
                )
                for subtask_id, issue_number, pr_number in subtask_prs
            ),
            session_external_id=session_handle.external_id,
            session_external_url=session_handle.external_url,
        )
    )
    save_integration_review_state(state, state_path)


def record_pending_not_needed_review(
    state_path: str | Path,
    issue_number: int,
    subtask_id: str,
    session_handle: DispatchHandle,
) -> None:
    """#282: `dispatch_not_needed_review`直後に呼び、後続サイクルでの
    ポーリング対象として記録する。"""
    state = load_not_needed_review_state(state_path)
    state.pending.append(
        PendingNotNeededReview(
            issue_number=issue_number,
            subtask_id=subtask_id,
            dispatched_at=time.time(),
            session_external_id=session_handle.external_id,
            session_external_url=session_handle.external_url,
        )
    )
    save_not_needed_review_state(state, state_path)


def process_pending_not_needed_reviews(state_path: str | Path) -> dict:
    """#282: 保留中の`status:not-needed`検証レビューをポーリングし、検証に通った
    ものはIssueを決定論的にクローズする。レビューセッション自身はクローズを
    実行しないため、この関数が「クローズしても問題ないものを実際にクローズする」
    実行主体を担う。

    - `not-needed-review:passed` を検知 → Issueをクローズし、人間へメンションした
      コメントを残す（事後の可視性確保）。ラベルを外して記録を消費する。
    - `not-needed-review:failed` を検知 → `status:queued`への差し戻しは既に
      レビューセッション自身が行っているため、Python側はラベルを外して記録を
      消費するのみ。
    - どちらのラベルもまだ無ければ、記録はそのまま保持し次サイクルで再確認する。
    """
    state = load_not_needed_review_state(state_path)
    if not state.pending:
        return {"closed": [], "reopened": [], "still_pending": 0}

    still_pending: list[PendingNotNeededReview] = []
    closed_summary: list[int] = []
    reopened_summary: list[int] = []

    for entry in state.pending:
        try:
            labels = github.get_issue_labels(entry.issue_number)
        except Exception as exc:  # noqa: BLE001 - GitHub障害でクラッシュさせない
            print(
                f"Warning: failed to poll labels for issue "
                f"{entry.issue_number}: {exc}",
                file=sys.stderr,
            )
            still_pending.append(entry)
            continue

        if NOT_NEEDED_VERIFIED_LABEL in labels:
            github.remove_label(entry.issue_number, NOT_NEEDED_VERIFIED_LABEL)
            github.close_issue(
                entry.issue_number,
                "not planned",
                comment=(
                    f"{NOT_NEEDED_ATTENTION_MENTION} "
                    "独立したレビューセッションでも対応不要と確認できたため、"
                    "自動的にクローズしました。誤りであれば再オープンしてください。"
                ),
            )
            closed_summary.append(entry.issue_number)
        elif NOT_NEEDED_REJECTED_LABEL in labels:
            github.remove_label(entry.issue_number, NOT_NEEDED_REJECTED_LABEL)
            reopened_summary.append(entry.issue_number)
        else:
            still_pending.append(entry)

    save_not_needed_review_state(
        NotNeededReviewState(pending=still_pending), state_path
    )
    return {
        "closed": closed_summary,
        "reopened": reopened_summary,
        "still_pending": len(still_pending),
    }
