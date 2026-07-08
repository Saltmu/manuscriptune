"""#186: 仮マージCI通過後の最終防衛線となるLLM統合コーディネーター。

仮マージCIが全通過した「成功」状態のときのみ、dispatcherと**同一のClaude Code
汎用ルーチン**（`ORCHESTUNE_ROUTINE_ID`/`ORCHESTUNE_ROUTINE_TOKEN`）を起動して
意味的レビューを行う。起動されたClaude Codeセッションが仮マージブランチの結合diffを
検証し、DAGでは検知できない意味的バグ（同一のグローバル設定に対する競合する利用など）を
探す。問題がなければ人間へマージ可能通知を、問題があれば原因サブタスクの差し戻しを、
セッション自身がGitHub上で行う（dispatcherがルーチンでPRを開くのと同じ非同期・
GitHub媒介パターン）。**最終的なPRマージは従来通り人間が行う（自動マージしない）。**

差し戻し後の再レビューは、fireのたびに前回の指摘を記憶しない新規のClaude Code
セッションが起動されるため、判断のバイアスが自然に避けられる
（metaswarmプロジェクトの知見と整合）。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol

from src.dispatch_targets import (
    ROUTINE_ID_ENV_VAR,
    ROUTINE_TOKEN_ENV_VAR,
    ClaudeCodeCloudRoutineDispatchTarget,
    DispatchHandle,
)


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
        "3. 判定に応じて次のいずれかをGitHub上で実施する（自動マージは絶対に行わない）:\n"
        f"   - 問題なし → 親Issue {parent_ref} に「🎉 意味的レビュー通過、人手での"
        f"最終マージが可能」というコメントを投稿する。\n"
        "   - 問題あり → 原因となったサブタスクのIssueについて、ラベルを "
        "`status:done` から `status:queued` へ付け替え、検出した問題の具体的な説明を"
        f"コメントする。あわせて親Issue {parent_ref} に差し戻した旨を残す。\n"
        "前回のレビュー内容は与えられていません。今回のdiffだけを根拠に判断してください。"
    )


class IntegrationCoordinator:
    """dispatcherと同一のルーチンを起動して意味的レビューを委譲する。

    `dispatch_review()` は毎回ルーチンをfireするだけで、判定と後続アクション
    （マージ可能通知 or 差し戻し）は起動されたClaude Codeセッションが担う。
    fireのたびに新規セッションが立つため、再レビュー時も前回の指摘を引き継がない。
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
