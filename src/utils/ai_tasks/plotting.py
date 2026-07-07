from typing import Any

from src.utils.ai_tasks.base import AgyTask


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


class PlotExpansionTask(AgyTask[PlotExpansionInput, str]):
    """既存プロットを、GMCO・三幕構成の観点を満たす形で肉付け（詳細化）する。

    プロンプトの実処理は #248 で実装する。
    """

    def execute(self, input_data: PlotExpansionInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: PlotExpansionInput) -> str:
        return input_data.plot_content


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
    """統合済みfindings YAMLの指摘をすべて解消する形でプロットを改稿する。

    プロンプトの実処理は #248 で実装する。
    """

    def execute(self, input_data: PlotRevisionInput, callback: Any = None) -> str:  # type: ignore[override]
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt, callback=callback)
        return self.postprocess(raw_output, input_data)

    def render_prompt(self, input_data: PlotRevisionInput) -> str:
        return input_data.plot_content
