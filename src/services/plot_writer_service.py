"""プロット作成（肉付け・findings反映改稿）のビジネスロジック。

本モジュールは #247 の契約定義であり、シグネチャ・エラー処理のみを確定する。
実際のプロンプト内容は #248、ドラフト保存とdata/sourcesガードレールは #249 で実装する。
"""

import os
from collections.abc import Callable
from typing import Any

from src.utils import project_paths
from src.utils.ai_task import (
    PlotExpansionInput,
    PlotExpansionTask,
    PlotRevisionInput,
    PlotRevisionTask,
)
from src.utils.cancellation import CancellationToken
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "Gemini 3.5 Flash (High)"


class PlotWriterServiceError(Exception):
    """プロットファイル未検出やfindings未生成など、プロット作成処理の実行時エラー。"""


def expand_plot(
    *,
    plot_file: str,
    model: str | None = None,
    focus_instructions: str | None = None,
    cancel_token: CancellationToken | None = None,
    on_line: Callable[[str], None] | None = None,
    **_unused: Any,
) -> str:
    """既存プロットを肉付けし、生成されたドラフト本文を返す。

    ドラフトの保存処理は #249 で実装する。
    """
    if not os.path.exists(plot_file):
        raise PlotWriterServiceError(f"Plot file not found: {plot_file}")

    if cancel_token:
        cancel_token.check()

    plot_content = read_file(plot_file)
    task = PlotExpansionTask(model=model or DEFAULT_MODEL)
    input_data = PlotExpansionInput(
        plot_content=plot_content,
        focus_instructions=focus_instructions,
    )

    def callback(line: str) -> None:
        if on_line:
            on_line(line)

    return task.execute(input_data, callback=callback)


def revise_plot_with_findings(
    *,
    plot_file: str,
    model: str | None = None,
    cancel_token: CancellationToken | None = None,
    on_line: Callable[[str], None] | None = None,
    **_unused: Any,
) -> str:
    """統合済みfindings YAMLの指摘を反映してプロットを改稿し、生成されたドラフト本文を返す。

    ドラフトの保存処理は #249 で実装する。
    """
    if not os.path.exists(plot_file):
        raise PlotWriterServiceError(f"Plot file not found: {plot_file}")

    plot_stem = os.path.splitext(os.path.basename(plot_file))[0]
    findings_yaml_path = project_paths.get_plot_findings_yaml_path(
        project_paths.get_output_dir(plot_stem), plot_stem
    )
    if not os.path.exists(findings_yaml_path):
        raise PlotWriterServiceError(
            f"Integrated plot findings YAML not found: {findings_yaml_path}"
        )

    if cancel_token:
        cancel_token.check()

    plot_content = read_file(plot_file)
    findings_yaml = read_file(findings_yaml_path)
    task = PlotRevisionTask(model=model or DEFAULT_MODEL)
    input_data = PlotRevisionInput(
        plot_content=plot_content,
        findings_yaml=findings_yaml,
    )

    def callback(line: str) -> None:
        if on_line:
            on_line(line)

    return task.execute(input_data, callback=callback)
