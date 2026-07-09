import re
from typing import Any

from src.utils import project_config as writer_helper
from src.utils.ai_tasks.base import AgyTask
from src.utils.file_io import read_file


class PlotExpansionInput:
    """Input structure for PlotExpansionTask."""

    def __init__(
        self,
        plot_content: str,
        character: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
        focus_instructions: str | None = None,
    ):
        self.plot_content = plot_content
        self.character = character
        self.policy_global = policy_global
        self.policy_chapter = policy_chapter
        self.focus_instructions = focus_instructions


def _resolve_policy_and_character(
    character: str | None, policy_global: str | None, policy_chapter: str | None
) -> tuple[str, str, str]:
    character_path = character or writer_helper.resolve_novel_file_by_pattern(
        "character",
        "*キャラクター概要*.txt",
        "data/sources/03_1_第1幕キャラクター概要 ver.2.txt",
    )
    policy_global_path = policy_global or writer_helper.resolve_novel_file_by_pattern(
        "policy_global",
        "*執筆ポリシー_全体*.txt",
        "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt",
    )
    policy_chapter_path = policy_chapter or writer_helper.resolve_novel_file_by_pattern(
        "policy_chapter",
        "*執筆ポリシー_第*.txt",
        "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt",
    )
    return (
        read_file(character_path),
        read_file(policy_global_path),
        read_file(policy_chapter_path),
    )


def _strip_code_fence(text: str) -> str:
    content = text.strip()
    content = re.sub(r"^```[a-zA-Z]*\n", "", content)
    content = re.sub(r"\n```$", "", content).strip()
    return content


class PlotExpansionTask(AgyTask[PlotExpansionInput, str]):
    """既存プロットを、GMCO・三幕構成の観点を満たす形で肉付け（詳細化）する。"""

    def execute(self, input_data: PlotExpansionInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: PlotExpansionInput) -> str:
        character_text, policy_global_text, policy_chapter_text = (
            _resolve_policy_and_character(
                input_data.character,
                input_data.policy_global,
                input_data.policy_chapter,
            )
        )

        focus_block = ""
        if input_data.focus_instructions:
            focus_block = f"""==============================
【肉付けの重点指示（ユーザー指定）】
{input_data.focus_instructions}
"""

        prompt = f"""あなたは物語の「エンジン（推進力）」と「骨格」の両方を設計するプロット構成エージェントです。
以下の「元プロット」を、各シーンが以下のGMCOフレームワークおよび三幕構成の観点を満たすように詳細化（肉付け）してください。

【GMCOフレームワーク（シーン単位）】
- G: Goal（目標） - そのシーンでキャラクターが達成しようとしていることを明確にする。
- M: Conflict（障害） - 目標達成を妨げる外的・内的な障害を設計する。
- C: Choice（選択・葛藤） - キャラクターに代償を伴う選択を迫る。
- O: Outcome（結果） - シーンの終わりに状況を変化させ、次のシーンへのフックを作る。

【三幕構成・感情の弧の観点】
- 第一幕（発端）・第二幕（対立・展開）・第三幕（解決）の役割を踏まえ、中だるみが生じないようにする。
- 主人公の感情・内的状態の変化（エモーショナルアーク）が伝わるようにする。
- ターニングポイントとクライマックスの緊張の高まりを意識する。

==============================
【執筆ポリシー】
{policy_global_text}

{policy_chapter_text}
==============================
【キャラクター概要】
{character_text}
==============================
{focus_block}==============================
【元プロット】
{input_data.plot_content}
==============================

【出力指示】
・上記の観点を踏まえ、元プロットを詳細化した「プロット全文」のみを出力してください。
・「第N章：」「第N話：」の章・話見出し、および「シーンN：」で始まるシーン構造は、元プロットの構成を維持したまま出力してください（見出し・シーン区切りを削除・統合しないこと）。
・解説、挨拶、確認などのメタなテキストやマークダウンのコードブロック（```）は一切出力しないでください。
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: PlotExpansionInput) -> str:
        return _strip_code_fence(raw_output)


class PlotRevisionInput:
    """Input structure for PlotRevisionTask."""

    def __init__(
        self,
        plot_content: str,
        findings_yaml: str,
        character: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
    ):
        self.plot_content = plot_content
        self.findings_yaml = findings_yaml
        self.character = character
        self.policy_global = policy_global
        self.policy_chapter = policy_chapter


class PlotRevisionTask(AgyTask[PlotRevisionInput, str]):
    """統合済みfindings YAMLの指摘をすべて解消する形でプロットを改稿する。"""

    def execute(self, input_data: PlotRevisionInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: PlotRevisionInput) -> str:
        character_text, policy_global_text, policy_chapter_text = (
            _resolve_policy_and_character(
                input_data.character,
                input_data.policy_global,
                input_data.policy_chapter,
            )
        )

        prompt = f"""あなたは物語のプロットを担当する優秀な構成編集者です。
【元プロット】について、統合済みの【指摘事項（findings）】をすべて解消するように改稿してください。

==============================
【執筆ポリシー】
{policy_global_text}

{policy_chapter_text}
==============================
【キャラクター概要】
{character_text}
==============================
【指摘事項（findings）】
{input_data.findings_yaml}
==============================
【元プロット】
{input_data.plot_content}
==============================

【出力指示】
・指摘事項に挙げられた問題点をすべて解消した、改稿後の「プロット全文」のみを出力してください。
・「第N章：」「第N話：」の章・話見出し、および「シーンN：」で始まるシーン構造は、元プロットの構成を維持したまま出力してください（見出し・シーン区切りを削除・統合しないこと）。
・指摘されていない箇所の展開・トーン・キャラクター描写は不必要に変更しないでください。
・解説、挨拶、確認などのメタなテキストやマークダウンのコードブロック（```）は一切出力しないでください。
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: PlotRevisionInput) -> str:
        return _strip_code_fence(raw_output)
