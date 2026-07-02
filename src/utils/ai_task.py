import os
import re
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from src.utils import project_config as writer_helper
from src.utils.ai_client import AgyClient
from src.utils.file_io import read_file

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgyTask(ABC, Generic[InputT, OutputT]):
    """Base class representing a task to be processed via AgyClient.

    Encapsulates preprocessing, prompt rendering, execution, and postprocessing.
    """

    def __init__(
        self,
        model: str = "Gemini 3.5 Flash (High)",
        client: AgyClient | None = None,
    ):
        self.model = model
        self.client = client or AgyClient(model=model)

    def execute(self, *args: Any, **kwargs: Any) -> OutputT:
        """Executes the task step-by-step using the Template Method pattern."""
        input_data = self.preprocess(*args, **kwargs)
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt)
        return self.postprocess(raw_output, input_data)

    def preprocess(self, *args: Any, **kwargs: Any) -> InputT:
        """Processes raw inputs into the structured input data required by the task."""
        if len(args) == 1 and not kwargs:
            return args[0]  # type: ignore
        return kwargs  # type: ignore

    @abstractmethod
    def render_prompt(self, input_data: InputT) -> str:
        """Renders the final prompt string using the input data."""
        pass

    def postprocess(self, raw_output: str, input_data: InputT) -> OutputT:
        """Parses, cleanses, or validates the raw LLM output into the final output format."""
        return raw_output  # type: ignore


# =====================================================================
# 1. ReviewSkillTask
# =====================================================================

_CONTEXT_BUILDERS = {
    "text-reviewer-logic": "_get_text_logic_context",
    "text-reviewer-style": "_get_text_style_context",
    "plot-reviewer-conflict": "_get_plot_conflict_context",
    "plot-reviewer-structure": "_get_plot_structure_context",
}


class ReviewSkillInput:
    """Input structure for ReviewSkillTask."""

    def __init__(self, skill_name: str, target_text: str, output_dir: str):
        self.skill_name = skill_name
        self.target_text = target_text
        self.output_dir = output_dir


class ReviewSkillTask(AgyTask[ReviewSkillInput, str]):
    """Executes a specific review skill to check novel content and return YAML findings."""

    def render_prompt(self, input_data: ReviewSkillInput) -> str:
        skill_name = input_data.skill_name
        target_text = input_data.target_text
        output_dir = input_data.output_dir

        skill_md_path = os.path.join("skills", skill_name, "SKILL.md")
        if not os.path.exists(skill_md_path):
            raise FileNotFoundError(
                f"SKILL.md not found for skill '{skill_name}' at {skill_md_path}"
            )

        skill_instruction = read_file(skill_md_path)

        def get_latest_file(pattern_key: str, default_pattern: str) -> str | None:
            return writer_helper.resolve_novel_file_by_pattern(  # type: ignore[no-any-return]
                pattern_key, default_pattern, None
            )

        method_name = _CONTEXT_BUILDERS.get(skill_name)
        if method_name:
            builder = getattr(self, method_name)
            context_text = builder(get_latest_file, output_dir)
        else:
            context_text = ""

        target_label = (
            "【校閲対象のプロットテキスト】"
            if skill_name.startswith("plot-")
            else "【校閲対象の小説テキスト】"
        )

        prompt = f"""{skill_instruction}

==============================
{context_text}
==============================

==============================
{target_label}
{target_text}
==============================

【実行指示】
上記のテキストに対し、あなたの役割に従って校閲を行ってください。
指摘事項がある場合は、指定されたYAML形式で出力してください。
・出力は必ず ```yaml で始まるYAMLコードブロックのみにしてください。
・挨拶や解説などのメタなテキストは一切出力しないでください。
・もし指摘事項がない場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```
"""
        return prompt

    def _get_text_logic_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        filtered_context_path = os.path.join(output_dir, "01_filtered_context.txt")
        if os.path.exists(filtered_context_path):
            context_text += f"\n【フィルタリング済み設定資料】\n{read_file(filtered_context_path)}\n"
        else:
            setting_file = get_latest_file("settings", "*設定資料集*.txt")
            char_file = get_latest_file("character", "*キャラクター概要*.txt")
            plot_file = get_latest_file("plot", "*プロット*.txt")
            if setting_file:
                context_text += f"\n【設定資料集】\n{read_file(setting_file)}\n"
            if char_file:
                context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
            if plot_file:
                context_text += f"\n【プロット】\n{read_file(plot_file)}\n"
        return context_text

    def _get_text_style_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        policy_file = get_latest_file("policy_global", "*執筆ポリシー_全体*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if policy_file:
            context_text += f"\n【執筆ポリシー】\n{read_file(policy_file)}\n"
        return context_text

    def _get_plot_conflict_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        policy_file = get_latest_file("policy_global", "*執筆ポリシー_全体*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if policy_file:
            context_text += f"\n【執筆ポリシー】\n{read_file(policy_file)}\n"
        return context_text

    def _get_plot_structure_context(self, get_latest_file, output_dir: str) -> str:
        context_text = ""
        char_file = get_latest_file("character", "*キャラクター概要*.txt")
        setting_file = get_latest_file("settings", "*設定資料集*.txt")
        if char_file:
            context_text += f"\n【キャラクター概要】\n{read_file(char_file)}\n"
        if setting_file:
            context_text += f"\n【設定資料集】\n{read_file(setting_file)}\n"
        return context_text

    def postprocess(self, raw_output: str, input_data: ReviewSkillInput) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


# =====================================================================
# 2. BlockReplacementTask
# =====================================================================


class BlockReplacementInput:
    """Input structure for BlockReplacementTask."""

    def __init__(self, context_lines: list[str], findings_in_block: list[dict]):
        self.context_lines = context_lines
        self.findings_in_block = findings_in_block


class BlockReplacementTask(AgyTask[BlockReplacementInput, str | None]):
    """Instructs LLM to rewrite a text block according to the provided review findings."""

    def render_prompt(self, input_data: BlockReplacementInput) -> str:
        context_lines = input_data.context_lines
        findings_in_block = input_data.findings_in_block

        context_text_with_line_numbers = ""
        for idx, line in enumerate(context_lines):
            context_text_with_line_numbers += f"{idx + 1}: {line}"

        findings_str = ""
        for f_idx, f in enumerate(findings_in_block):
            findings_str += f"■ 指摘 {f_idx + 1}\n"
            findings_str += f"・対象原文: {f.get('original')}\n"
            findings_str += f"・指摘内容: {f.get('suggestion')}\n\n"

        prompt = f"""あなたは小説の優秀な編集者です。
以下の【元のテキストブロック】に対して、提示された【修正指示】をすべて反映した、修正後のテキストブロックを生成してください。

【元のテキストブロック】
{context_text_with_line_numbers}

【修正指示】
{findings_str}

【指示・ルール】
・【元のテキストブロック】の各行の先頭には「行番号: 」が付いています。これを参考に、指定された「対象原文」の箇所を修正してください。
・修正する際は、周囲の文脈やキャラクターの口調、文章のリズムに自然に馴染むように書き換えてください。不自然な繋ぎ目にならないように配慮してください。
・出力は、修正・書き換えを行った「テキストブロック全体」としてください。
- 出力するテキストブロックには、行番号（「1: 」など）や、解説、挨拶、マークダウンのコードブロック（```）などは一切含めないでください。純粋な小説の本文のみを出力してください。
・行数は元のテキストブロックとおおむね同程度とし、修正指示に関係のない部分は元の文章をそのまま維持してください。
"""
        return prompt

    def postprocess(
        self, raw_output: str, input_data: BlockReplacementInput
    ) -> str | None:
        result = raw_output.strip()

        # Clean up markdown formatting
        result = re.sub(r"^```[a-zA-Z]*\n", "", result)
        result = re.sub(r"\n```$", "", result).strip()

        # Guard: if LLM output is too short (e.g. LLM failed and returned generic message or empty)
        original_length = sum(len(line) for line in input_data.context_lines)
        if len(result) < original_length * 0.3:
            return None

        # Strip line numbers if the LLM output includes them
        lines = result.splitlines()
        has_line_numbers = all(
            re.match(r"^\d+\s*:\s*", line) for line in lines if line.strip()
        )
        if has_line_numbers and len(lines) > 0:
            cleaned_lines = []
            for line in lines:
                cleaned_line = re.sub(r"^\d+\s*:\s*", "", line)
                cleaned_lines.append(cleaned_line)
            result = "\n".join(cleaned_lines)

        return result


# =====================================================================
# 3. FindingsIntegrationTask
# =====================================================================


class FindingsIntegrationInput:
    """Input structure for FindingsIntegrationTask."""

    def __init__(self, target_text: str, raw_findings_text: str):
        self.target_text = target_text
        self.raw_findings_text = raw_findings_text


class FindingsIntegrationTask(AgyTask[FindingsIntegrationInput, str]):
    """Merges and resolves conflicts from multiple raw finding lists into a consolidated YAML."""

    def render_prompt(self, input_data: FindingsIntegrationInput) -> str:
        target_text = input_data.target_text
        raw_findings_text = input_data.raw_findings_text

        prompt = f"""あなたは小説の編集長です。
校閲エージェントから提出された同一の小説章に対する校閲指摘リスト（YAML）を精査し、以下のルールに従って1つの統合された指摘リスト（YAML）を作成してください。

【マージルール】
1. **重複の排除**: 同じ箇所の同じような指摘は、最も具体的で有益な内容に統合してください。
2. **競合の解決**: 表現側の提案が世界観やキャラクター設定に反している場合は、設定側のルールを最優先し、表現側の提案を設定に矛盾しないように調整または棄却してください。
3. **重要度による絞り込み**: 優先順位（severity: high > medium > low）を考慮し、重要度の低い些細な指摘は削除し、全体で最大20〜25件程度に抑えてください。
4. **IDの振り直し**: 統合後の指摘に対して、`INT-001`, `INT-002` ... と連番でIDを振り直してください。
5. **出力フォーマット**:
   - 必ず `findings` キーを持つ配列形式のYAMLコードブロック（```yaml ... ```）のみを出力してください。
   - 挨拶や解説などのメタなテキストは一切出力しないでください。
   - 各 finding の構造は以下のキーを厳密に保持してください：
     - `id` (INT-XXX)
     - `location` (元の指摘の行数)
     - `original` (該当箇所のテキスト抜粋。元の指摘リストにある `original` や【校閲対象の小説テキスト】から、一切の改変（文字の追加、削除、表現の翻訳、誤植 of 修正、勝手な省略など）をせず、一字一句違わずにそのままコピーして抽出してください。「カップの縁」を「カップ of 縁」と表現を変えるなどの改変は絶対に禁止します)
     - `category` (カテゴリ名)
     - `severity` (high / medium / low / info)
     - `analysis` (統合・競合解決された分析内容)
     - `suggestion` (統合・調整された修正案)
     - `accepted` ("n" で固定)

もし指摘事項がなくなった場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```

【校閲対象の小説テキスト】
==============================
{target_text}
==============================

【検出された校閲指摘リスト】
==============================
{raw_findings_text}
==============================
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: FindingsIntegrationInput) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


# =====================================================================
# 4. PlotFindingsIntegrationTask
# =====================================================================


class PlotFindingsIntegrationInput:
    """Input structure for PlotFindingsIntegrationTask."""

    def __init__(self, target_text: str, raw_findings_text: str):
        self.target_text = target_text
        self.raw_findings_text = raw_findings_text


class PlotFindingsIntegrationTask(AgyTask[PlotFindingsIntegrationInput, str]):
    """Merges and resolves conflicts from multiple raw plot finding lists into a consolidated YAML."""

    def render_prompt(self, input_data: PlotFindingsIntegrationInput) -> str:
        target_text = input_data.target_text
        raw_findings_text = input_data.raw_findings_text

        prompt = f"""あなたはプロットの構成監修者です。
校閲エージェントから提出された同一のプロットに対する校閲指摘リスト（YAML）を精査し、以下のルールに従って1つの統合された指摘リスト（YAML）を作成してください。

【マージルール】
1. **重複の排除**: 同じ箇所の同じような指摘は、最も具体的で有益な内容に統合してください。
2. **設定との一貫性**: 指摘や提案内容が世界観やキャラクター設定に反している場合は、設定側のルールを最優先し、それに矛盾しないように調整または棄却してください。
3. **重要度による絞り込み**: 優先順位（severity: high > medium > low）を考慮し、重要度の低い些細な指摘は削除し、全体で最大20〜25件程度に抑えてください。
4. **IDの振り直し**: 統合後の指摘に対して、`PINT-001`, `PINT-002` ... と連番でIDを振り直してください。
5. **出力フォーマット**:
   - 必ず `findings` キーを持つ配列形式のYAMLコードブロック（```yaml ... ```）のみを出力してください。
   - 挨拶や解説などのメタなテキストは一切出力しないでください。
   - 各 finding の構造は以下のキーを厳密に保持してください：
     - `id` (PINT-XXX)
     - `location` (元の指摘の場所・シーン名等)
     - `original` (該当箇所のテキスト抜粋。元の指摘リストにある `original` や【校閲対象 of プロットテキスト】から、一切の改変（文字の追加、削除、表現の翻訳、誤植の修正、勝手な省略など）をせず、一字一句違わずにそのままコピーして抽出してください)
     - `category` (カテゴリ名)
     - `severity` (high / medium / low / info)
     - `analysis` (統合・競合解決された分析内容)
     - `suggestion` (統合・調整された修正案)
     - `accepted` ("n" で固定)

もし指摘事項がなくなった場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```

【校閲対象のプロットテキスト】
==============================
{target_text}
==============================

【検出された校閲指摘リスト】
==============================
{raw_findings_text}
==============================
"""
        return prompt

    def postprocess(
        self, raw_output: str, input_data: PlotFindingsIntegrationInput
    ) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


# =====================================================================
# 5. NovelWritingTask
# =====================================================================


class NovelWritingInput:
    """Input structure for NovelWritingTask."""

    def __init__(
        self,
        chapter_title: str,
        episode_title: str,
        plot_content: str,
        novel_title: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
        character: str | None = None,
        previous_episode_text: str | None = None,
        neighbor_plots_block: str | None = None,
    ):
        self.chapter_title = chapter_title
        self.episode_title = episode_title
        self.plot_content = plot_content
        self.novel_title = novel_title
        self.policy_global = policy_global
        self.policy_chapter = policy_chapter
        self.character = character
        self.previous_episode_text = previous_episode_text
        self.neighbor_plots_block = neighbor_plots_block


class NovelWritingTask(AgyTask[NovelWritingInput, str]):
    """Writes a full novel episode based on prompt parameters."""

    def execute(self, input_data: NovelWritingInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: NovelWritingInput) -> str:
        policy_global = (
            input_data.policy_global
            or writer_helper.resolve_novel_file_by_pattern(
                "policy_global",
                "*執筆ポリシー_全体*.txt",
                "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt",
            )
        )
        policy_chapter = (
            input_data.policy_chapter
            or writer_helper.resolve_novel_file_by_pattern(
                "policy_chapter",
                "*執筆ポリシー_第*.txt",
                "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt",
            )
        )
        character = input_data.character or writer_helper.resolve_novel_file_by_pattern(
            "character",
            "*キャラクター概要*.txt",
            "data/sources/03_1_第1幕キャラクター概要 ver.2.txt",
        )

        policy_text = read_file(policy_global)
        policy_macro_text = read_file(policy_chapter)
        character_text = read_file(character)

        prev_context_block = ""
        if input_data.previous_episode_text:
            prev_context_block = f"""
==============================
【前話（直前のエピソード）の終盤描写】
（※前話からの展開、キャラクターの状況、会話のトーン等の繋がりを維持するために参考にしてください）
{input_data.previous_episode_text}
==============================
"""

        actual_title = input_data.novel_title or writer_helper.get_novel_setting(
            "title", "重天の調律師"
        )

        neighbor_block = ""
        if input_data.neighbor_plots_block:
            neighbor_block = f"""==============================
{input_data.neighbor_plots_block.strip()}
"""

        prompt = f"""【超重要指示：ツールの使用禁止】
    あなたは一切のツール（ファイルの読み書き、ディレクトリの確認、コマンドの実行など）を使用してはなりません。
    プロジェクトの調査や他のスクリプト（writer_cli.pyなど）の実行を決して試みないでください。
    思考プロセスや挨拶、指示の確認などのメタなテキストは一切出力せず、ただちに小説の本文のみをテキスト出力してください。
    あなたの唯一のタスクは、提示された以下の執筆ポリシー、キャラクター概要、およびプロットに基づき、小説の本文のみをただちに出力することです。
    本文の最初の1文字目から出力を開始してください。

あなたは「{actual_title}」シリーズの専属作家です。
以下の「執筆ポリシー」「キャラクター概要」を完全に把握し、ポリシーを厳守して物語を綴ってください。

==============================
【執筆ポリシー】
{policy_text}

{policy_macro_text}
==============================
{prev_context_block}==============================
【キャラクター概要】
{character_text}
==============================
{neighbor_block}==============================
【今回執筆する対象のプロット】
対象: {input_data.chapter_title} {input_data.episode_title}

{input_data.plot_content}
==============================

【執筆指示】
上記のプロットに従い、「{input_data.chapter_title} {input_data.episode_title}」の本文を執筆してください。
・指示や注釈、挨拶などのメタなテキストは一切出力しないでください。小説の本文のみを出力してください。
・1話あたりの文字数に無理やり収めようとはせず、描写の密度を優先してください。
・執筆ポリシー（特に文体のリズム、特殊ルビ、地の文と会話のバランス、物理と叙情の描写）を必ず守ってください。

それでは、執筆を開始してください。
"""
        return prompt


# =====================================================================
# 6. NovelSceneWritingTask
# =====================================================================


class NovelSceneWritingInput:
    """Input structure for NovelSceneWritingTask."""

    def __init__(
        self,
        chapter_title: str,
        episode_title: str,
        scene_title: str,
        scene_plot: str,
        context_written: str,
        prev_context_block: str,
        novel_title: str | None = None,
        policy_global: str | None = None,
        policy_chapter: str | None = None,
        character: str | None = None,
        neighbor_plots_block: str | None = None,
    ):
        self.chapter_title = chapter_title
        self.episode_title = episode_title
        self.scene_title = scene_title
        self.scene_plot = scene_plot
        self.context_written = context_written
        self.prev_context_block = prev_context_block
        self.novel_title = novel_title
        self.policy_global = policy_global
        self.policy_chapter = policy_chapter
        self.character = character
        self.neighbor_plots_block = neighbor_plots_block


class NovelSceneWritingTask(AgyTask[NovelSceneWritingInput, str]):
    """Writes a single scene based on scene plot and already written context."""

    def execute(self, input_data: NovelSceneWritingInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: NovelSceneWritingInput) -> str:
        policy_global = (
            input_data.policy_global
            or writer_helper.resolve_novel_file_by_pattern(
                "policy_global",
                "*執筆ポリシー_全体*.txt",
                "data/sources/00_1_執筆ポリシー_全体_ver.6.0.txt",
            )
        )
        policy_chapter = (
            input_data.policy_chapter
            or writer_helper.resolve_novel_file_by_pattern(
                "policy_chapter",
                "*執筆ポリシー_第*.txt",
                "data/sources/00_2_執筆ポリシー_第1幕_ver1.2.txt",
            )
        )
        character = input_data.character or writer_helper.resolve_novel_file_by_pattern(
            "character",
            "*キャラクター概要*.txt",
            "data/sources/03_1_第1幕キャラクター概要 ver.2.txt",
        )

        policy_global_text = read_file(policy_global)
        policy_chapter_text = read_file(policy_chapter)
        character_text = read_file(character)

        scene_written_context = ""
        if input_data.context_written:
            scene_written_context = f"""==============================
【既に執筆済みの本文（シーンの流れ）】
{input_data.context_written}
"""

        neighbor_block = ""
        if input_data.neighbor_plots_block:
            neighbor_block = f"""==============================
{input_data.neighbor_plots_block.strip()}
"""

        prompt = f"""【超重要指示：ツールの使用禁止】
あなたは一切のツールを使用してはなりません。
思考プロセスやメタな解説などは一切出力せず、ただちに指定されたシーンの本文のみを出力してください。

    あなたは「{input_data.novel_title or "重天の調律師"}」の専属作家です。
以下の「執筆ポリシー」を厳守し、「既に執筆済みの本文」の展開、口調、描写リズムを自然に引き継いだ形で、「今回執筆する対象のシーンプロット」の本文を執筆してください。

==============================
【執筆ポリシー】
{policy_global_text}
{policy_chapter_text}
==============================
{input_data.prev_context_block}==============================
【キャラクター概要】
{character_text}
==============================
{neighbor_block}{scene_written_context}==============================
【今回執筆する対象のシーンプロット】
対象: {input_data.chapter_title} {input_data.episode_title}
現在のシーン: {input_data.scene_title}

{input_data.scene_plot}
==============================

【執筆指示】
「既に執筆済みの本文」の直後からシームレスに繋がるように、今回のシーン「{input_data.scene_title}」の本文のみを出力してください。
・挨拶や解説、マークダウンのコードブロック等は一切不要です。小説の本文のみを出力してください。
・前の文脈を繰り返さないでください。今回指定されたプロット部分のみを新しく書き足してください。
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: NovelSceneWritingInput) -> str:
        content = raw_output.strip()
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        content = re.sub(r"\n```$", "", content).strip()
        return content


# =====================================================================
# 7. NovelPolicyCheckTask
# =====================================================================


class NovelPolicyCheckInput:
    """Input structure for NovelPolicyCheckTask."""

    def __init__(
        self,
        novel_content: str,
        policy_text: str,
        policy_macro_text: str,
        plot_content: str,
    ):
        self.novel_content = novel_content
        self.policy_text = policy_text
        self.policy_macro_text = policy_macro_text
        self.plot_content = plot_content


class NovelPolicyCheckTask(AgyTask[NovelPolicyCheckInput, str]):
    """Performs policy self-verification on the generated novel content."""

    def render_prompt(self, input_data: NovelPolicyCheckInput) -> str:
        prompt = f"""あなたは小説の厳しい校閲編集者です。
提示された小説本文が、「執筆ポリシー」および「演出指示・禁止事項」を満たしているか厳密にチェックしてください。

==============================
【執筆ポリシー】
{input_data.policy_text}

{input_data.policy_macro_text}
==============================

【指示】
上記の小説本文をポリシーおよび禁止事項と照らし合わせ、違反している箇所を検出してください。
出力は必ず ```yaml で始まるYAMLコードブロックのみにしてください。
メタな解説や挨拶は一切含めないでください。

指摘事項がある場合は、以下のように出力してください：
```yaml
violations:
  - original: "（違反のある原文の抜粋）"
    reason: "（違反の理由。例：禁止語『ネフェス』が使用されています）"
    suggestion: "（どのように修正すべきかの具体的な提案。例：『重力制御』または『調律』と書き換えてください）"
```

もし違反が一切ない場合は、空のリストを出力してください：
```yaml
violations: []
```

==============================
【プロットと演出指示・禁止事項】
{input_data.plot_content}
==============================

==============================
【小説本文】
{input_data.novel_content}
==============================
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: NovelPolicyCheckInput) -> str:
        result = raw_output.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result


# =====================================================================
# 8. NovelRewriteTask
# =====================================================================


class NovelRewriteInput:
    """Input structure for NovelRewriteTask."""

    def __init__(self, novel_content: str, yaml_content: str):
        self.novel_content = novel_content
        self.yaml_content = yaml_content


class NovelRewriteTask(AgyTask[NovelRewriteInput, str]):
    """Rewrites the novel content to resolve detected policy violations."""

    def render_prompt(self, input_data: NovelRewriteInput) -> str:
        prompt = f"""あなたは小説の優秀な編集者です。
【小説本文】について、検出された【指摘事項】をすべて解消するように適切に書き換えてください。

【出力ルール】
・修正・書き換え後の小説本文全体のみを出力してください。
・解説、挨拶、マークダウンのコードブロック（```）などは一切出力しないでください。
・指摘された問題点（語彙、設定矛盾、表現など）のみを解消し、文体やニュアンスはそのまま維持してください。

==============================
【検出された指摘事項】
{input_data.yaml_content}
==============================

==============================
【小説本文】
{input_data.novel_content}
==============================
"""
        return prompt

    def postprocess(self, raw_output: str, input_data: NovelRewriteInput) -> str:
        rewritten_text = raw_output.strip()
        rewritten_text = re.sub(r"^```[a-zA-Z]*\n", "", rewritten_text)
        rewritten_text = re.sub(r"\n```$", "", rewritten_text).strip()
        return rewritten_text
