"""プロット作成（肉付け・findings反映改稿）のビジネスロジック。

生成したドラフトはdata/results配下に保存し、既存ドラフトはhistory/へ版管理して退避する。
data/sources/への書き込みはAIガードレールにより禁止しているため、保存前に検証する。
"""

import os
import re
import shutil
from collections.abc import Callable
from typing import Any

from src.utils import path_safety, project_paths
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

_VERSION_DIR_PATTERN = re.compile(r"^v(\d+)$")


class PlotWriterServiceError(Exception):
    """プロットファイル未検出やfindings未生成など、プロット作成処理の実行時エラー。"""


def _archive_existing_draft(output_dir: str, draft_path: str) -> None:
    """既存のドラフトをhistory/v{N}/へ退避してから上書きできるようにする。"""
    if not os.path.exists(draft_path):
        return

    history_dir = project_paths.get_history_dir(output_dir)
    os.makedirs(history_dir, exist_ok=True)

    existing_versions = [
        int(match.group(1))
        for d in os.listdir(history_dir)
        if os.path.isdir(os.path.join(history_dir, d))
        and (match := _VERSION_DIR_PATTERN.match(d))
    ]
    next_version = max(existing_versions) + 1 if existing_versions else 1
    version_dir = project_paths.get_version_dir(output_dir, f"v{next_version}")
    os.makedirs(version_dir, exist_ok=True)
    shutil.copy2(draft_path, os.path.join(version_dir, os.path.basename(draft_path)))


def _save_plot_draft(plot_file: str, content: str) -> str:
    """生成されたドラフト本文をdata/results配下に保存し、保存先パスを返す。

    data/sources/ 配下への書き込みはCLAUDE.mdのガードレールにより厳禁のため、
    apply_findingsと同水準のチェックを行う。
    """
    plot_stem = os.path.splitext(os.path.basename(plot_file))[0]
    output_dir = project_paths.get_output_dir(plot_stem)

    if path_safety.contains_source_segment(output_dir):
        raise PlotWriterServiceError(
            f"Writing plot drafts to {project_paths.DATA_SOURCES_DIR}/ is strictly "
            "prohibited by AI guardrails."
        )

    draft_path = project_paths.get_plot_draft_path(output_dir, plot_stem)
    _archive_existing_draft(output_dir, draft_path)

    os.makedirs(output_dir, exist_ok=True)
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    logger.info(f"Plot draft saved to {draft_path}")
    return draft_path


def expand_plot(
    *,
    plot_file: str,
    model: str | None = None,
    focus_instructions: str | None = None,
    cancel_token: CancellationToken | None = None,
    on_line: Callable[[str], None] | None = None,
    **_unused: Any,
) -> str:
    """既存プロットを肉付けし、生成したドラフトをdata/results配下に保存して本文を返す。"""
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

    result = task.execute(input_data, callback=callback)
    _save_plot_draft(plot_file, result)
    return result


def revise_plot_with_findings(
    *,
    plot_file: str,
    model: str | None = None,
    cancel_token: CancellationToken | None = None,
    on_line: Callable[[str], None] | None = None,
    **_unused: Any,
) -> str:
    """統合済みfindings YAMLの指摘を反映してプロットを改稿し、
    生成したドラフトをdata/results配下に保存して本文を返す。
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

    result = task.execute(input_data, callback=callback)
    _save_plot_draft(plot_file, result)
    return result
