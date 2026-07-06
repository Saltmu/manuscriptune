"""apply_findingsのビジネスロジック。src/cli/apply_findings.py と /api/stream/apply の共通実装。"""

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.findings.applier import (
    _apply_grouped_findings,
    _determine_accepted_findings,
    _group_findings,
    _save_outputs_and_print_summary,
)
from src.utils import path_safety, project_paths
from src.utils.cancellation import CancellationToken
from src.utils.file_io import read_file
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)


class ApplyFindingsValidationError(Exception):
    """ガードレール違反、または入力ファイルの欠落・破損により処理を開始できない場合に送出する。"""


@dataclass
class ApplyFindingsResult:
    applied_count: int
    skipped_count: int
    failed_count: int


def validate_output_dir(output_dir: str) -> None:
    if output_dir and path_safety.contains_source_segment(output_dir):
        raise ApplyFindingsValidationError(
            f"Writing to source files in {project_paths.DATA_SOURCES_DIR}/ is strictly "
            "prohibited by AI guardrails."
        )

    if not os.path.exists(output_dir):
        raise ApplyFindingsValidationError(f"Directory '{output_dir}' does not exist.")


def load_inputs(output_dir: str) -> tuple[str, str, list[str], list[dict], str]:
    basename = os.path.basename(os.path.abspath(output_dir))
    formatted_txt_path = project_paths.resolve_formatted_draft_path(
        output_dir, basename
    )
    findings_yaml_path = project_paths.resolve_findings_yaml_path(output_dir, basename)

    if not os.path.exists(formatted_txt_path):
        raise ApplyFindingsValidationError(f"'{formatted_txt_path}' not found.")
    if not os.path.exists(findings_yaml_path):
        raise ApplyFindingsValidationError(f"'{findings_yaml_path}' not found.")

    raw_text = read_file(formatted_txt_path)
    text_lines = raw_text.splitlines(keepends=True)

    try:
        yaml_data = YamlHandler.load(findings_yaml_path)
        findings = yaml_data.get("findings", []) if isinstance(yaml_data, dict) else []
    except Exception as e:
        raise ApplyFindingsValidationError(
            f"Error parsing YAML '{findings_yaml_path}': {e}"
        ) from e

    return formatted_txt_path, findings_yaml_path, text_lines, findings, basename


def apply_findings_in_dir(
    output_dir: str,
    *,
    interactive: bool = False,
    auto: bool = False,
    accept_ids: str | None = None,
    model: str = "Gemini 3.5 Flash (High)",
    no_llm: bool = False,
    cancel_token: CancellationToken | None = None,
    on_line: Callable[[str], None] | None = None,
    **_unused: Any,
) -> ApplyFindingsResult:
    """指摘(findings)を整形済みドラフトに反映する。CLIとFastAPIルートの共通実装。

    on_line は stream_service_call との呼び出し規約を揃えるためのキーワード引数だが、
    本処理は logger 経由の進捗報告のみを行うため未使用。
    """
    logger.info(f"Starting apply_findings for directory: {output_dir}")
    validate_output_dir(output_dir)

    formatted_txt_path, findings_yaml_path, text_lines, findings, _basename = (
        load_inputs(output_dir)
    )

    if not findings:
        logger.info("No findings to apply.")
        return ApplyFindingsResult(0, 0, 0)

    if not interactive and not accept_ids and not auto:
        logger.warning("No mode specified. Defaulting to interactive mode.")
        interactive = True

    args = argparse.Namespace(
        interactive=interactive,
        auto=auto,
        accept_ids=accept_ids,
        model=model,
        no_llm=no_llm,
    )

    active_findings = _determine_accepted_findings(findings, text_lines, args)
    logger.info(f"Determined {len(active_findings)} active findings to apply.")

    groups = _group_findings(active_findings)
    logger.info(f"Grouped active findings into {len(groups)} blocks.")

    cancel_check = cancel_token.check if cancel_token else None
    applied_count, failed_count = _apply_grouped_findings(
        text_lines, groups, args, cancel_check=cancel_check
    )

    if failed_count > 0:
        raise ApplyFindingsValidationError(
            f"安全対策ガードレール: {failed_count} 件の指摘の反映に失敗しました。"
            "小説テキストおよびYAMLファイルの変更を保存せず、元の状態を維持して処理を中断します。"
        )

    skipped_count = sum(1 for f in findings if f.get("accepted") != "y")
    stats = (applied_count, skipped_count, failed_count)

    _save_outputs_and_print_summary(
        formatted_txt_path, findings_yaml_path, text_lines, findings, stats
    )
    logger.info(
        f"Completed apply_findings. Stats: Applied={applied_count}, "
        f"Skipped={skipped_count}, Failed={failed_count}"
    )
    return ApplyFindingsResult(applied_count, skipped_count, failed_count)
