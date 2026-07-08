"""#186: 仮マージCI通過後の最終防衛線となるLLM統合コーディネーター。

仮マージCIが全通過した「成功」状態のときのみ、結合diffをLLMに渡し、
DAGでは検知できない意味的バグ（同一のグローバル設定に対する競合する利用など）を
検出する。パスすれば人間へマージ可能通知、問題があれば該当サブタスクを差し戻す。
**最終的なPRマージは従来通り人間が行う（このゲートは自動マージしない）。**

`dispatch_targets.py` と同様に、LLM呼び出しを注入可能な戦略（`Reviewer`）として
切り出すことでテスト容易性を確保する。差し戻し後の再レビューでは、前回の指摘を
記憶しない新規レビュアーインスタンスを使う（`review()`ごとに`reviewer_factory()`を
呼ぶ）ことで、判断のバイアスを避ける（metaswarmプロジェクトの知見を参考）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# プロンプト文字列を受け取り、モデルの回答テキストを返す戦略。
Reviewer = Callable[[str], str]


@dataclass(frozen=True)
class SemanticFinding:
    """意味的レビューで検出された1件の指摘（差し戻し対象サブタスクと理由）。"""

    subtask_id: str
    reason: str


@dataclass(frozen=True)
class SemanticReview:
    """統合コーディネーターによる意味的レビューの結果。"""

    passed: bool
    findings: tuple[SemanticFinding, ...] = ()
    raw: str = ""


def build_review_prompt(diff: str, merged_subtask_ids: Sequence[str]) -> str:
    """結合diffに対する意味的レビュー用プロンプトを構築する。

    再レビュー時のバイアス回避のため、過去の指摘内容は一切含めない。
    """
    subtask_list = ", ".join(merged_subtask_ids) if merged_subtask_ids else "(不明)"
    return (
        "あなたは複数の並列実装タスクを統合した仮マージブランチの最終レビュアーです。\n"
        "各サブタスクの単体CI（Ruff/Mypy/Pytest）は既に通過しています。\n"
        "あなたの唯一の役割は、静的解析やテストでは検知できない『意味的バグ』を\n"
        "結合diff全体から発見することです。特に次の観点を重視してください。\n"
        "- 同一のグローバル設定・共有状態・定数に対する、複数タスク間の競合する変更\n"
        "- 一方のタスクが変更した関数シグネチャ・契約に、他方が追随できていない不整合\n"
        "- 個々には正しいが結合すると破綻するロジック（重複した副作用・二重処理等）\n\n"
        f"統合対象サブタスク: {subtask_list}\n\n"
        "以下は仮マージブランチの結合diffです。\n"
        "-----BEGIN DIFF-----\n"
        f"{diff}\n"
        "-----END DIFF-----\n\n"
        "判定結果を、余計な文章を付けず次のJSONオブジェクトのみで出力してください。\n"
        '{"passed": <true|false>, "findings": '
        '[{"subtask_id": "<原因サブタスクID>", "reason": "<具体的な問題の説明>"}]}\n'
        "意味的バグが無ければ passed=true, findings=[] とします。"
    )


def _extract_json_object(text: str) -> dict | None:
    """テキスト中から最初のJSONオブジェクトを抽出してパースする。

    ```json フェンスや前後の地の文が混ざっていても、最初の`{`から対応する
    `}`までを括弧の深さで走査して取り出す。パースできなければ`None`。
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except (json.JSONDecodeError, ValueError):
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


class SubprocessReviewer:
    """既定Reviewer: Claude Codeヘッドレス(`claude -p`)をサブプロセス起動する。

    引数はリストで渡しシェルを経由しない（OSコマンドインジェクション対策）。
    CLAUDE.md準拠で最大`max_retries`回・指数バックオフのリトライを行う。
    """

    def __init__(
        self,
        command_prefix: Sequence[str] | None = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        timeout: float = 300.0,
    ):
        self._command_prefix = list(command_prefix or ["claude", "-p"])
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._timeout = timeout

    def __call__(self, prompt: str) -> str:
        args = [*self._command_prefix, prompt, "--output-format", "json"]
        stdout = self._run_with_retry(args)
        # Claude Code の --output-format json エンベロープから result を取り出す。
        try:
            envelope = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return stdout
        if isinstance(envelope, dict) and "result" in envelope:
            return str(envelope["result"])
        return stdout

    def _run_with_retry(self, args: list[str]) -> str:
        delay = self._initial_delay
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=self._timeout,
                )
                return result.stdout
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError,
            ) as exc:
                last_error = exc
            if attempt < self._max_retries:
                time.sleep(delay)
                delay *= 2
        assert last_error is not None
        raise last_error


class IntegrationCoordinator:
    """結合diffの意味的レビューを統括する。

    `review()`の呼び出しごとに`reviewer_factory()`を呼んで新しいReviewerを
    生成する。これにより差し戻し後の再レビューでも前回の指摘を引き継がない
    新規インスタンスが使われ、判断のバイアスを避けられる。
    """

    def __init__(
        self,
        reviewer_factory: Callable[[], Reviewer],
        repository_root: Path | None = None,
    ):
        self._reviewer_factory = reviewer_factory
        self._default_root = repository_root or Path(".")

    def review(
        self,
        repository_root: Path,
        base_branch: str,
        target_ref: str,
        merged_subtask_ids: Sequence[str],
    ) -> SemanticReview:
        diff = self._collect_diff(repository_root, base_branch, target_ref)
        if not diff.strip():
            # 差分が収集できない/空なら、CIは通過済みのため人手判断へ回す（フェイルセーフ）。
            return SemanticReview(
                passed=True, raw="(結合diffが空または収集できませんでした)"
            )

        prompt = build_review_prompt(diff, merged_subtask_ids)
        reviewer = self._reviewer_factory()  # 毎回新規インスタンス（バイアス回避）
        try:
            raw = reviewer(prompt)
        except Exception as exc:  # noqa: BLE001 - レビュー不能でパイプラインを止めない
            print(f"Warning: semantic reviewer failed: {exc}", file=sys.stderr)
            return SemanticReview(passed=True, raw=f"reviewer error: {exc}")

        return self._parse_review(raw)

    def _collect_diff(
        self, repository_root: Path, base_branch: str, target_ref: str
    ) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", f"{base_branch}...{target_ref}"],
                cwd=str(repository_root),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, OSError) as exc:
            print(
                f"Warning: failed to collect integration diff: {exc}", file=sys.stderr
            )
            return ""

    def _parse_review(self, raw: str) -> SemanticReview:
        obj = _extract_json_object(raw)
        if obj is None:
            # パース不能ならレビュー不能とみなし、人手判断へ回す（フェイルセーフ）。
            return SemanticReview(passed=True, raw=raw)

        passed = bool(obj.get("passed", True))
        findings: list[SemanticFinding] = []
        for entry in obj.get("findings", []) or []:
            if not isinstance(entry, dict):
                continue
            subtask_id = str(entry.get("subtask_id", "")).strip()
            reason = str(entry.get("reason", "")).strip()
            if subtask_id or reason:
                findings.append(SemanticFinding(subtask_id=subtask_id, reason=reason))

        return SemanticReview(passed=passed, findings=tuple(findings), raw=raw)


def build_integration_coordinator(
    repository_root: Path | None = None,
) -> IntegrationCoordinator:
    """既定構成の統合コーディネーターを構築する（Claude Codeヘッドレスを使用）。"""
    return IntegrationCoordinator(
        reviewer_factory=lambda: SubprocessReviewer(),
        repository_root=repository_root,
    )
