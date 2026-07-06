import re
from typing import Any

from src.utils import project_config as writer_helper
from src.utils.ai_tasks.base import AgyTask
from src.utils.file_io import read_file


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
