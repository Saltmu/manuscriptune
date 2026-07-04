import argparse
import os
import sys

from src.findings.applier import (
    _apply_grouped_findings,
    _determine_accepted_findings,
    _group_findings,
    _save_outputs_and_print_summary,
)
from src.utils import project_paths
from src.utils.file_io import read_file
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply integrated findings to formatted novel draft."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory containing 01_formatted.txt and 00_integrated_findings.yaml",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt user for each finding in the terminal.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically apply all findings marked as accepted: 'y'.",
    )
    parser.add_argument(
        "--accept-ids",
        help="Comma-separated list of finding IDs to accept and apply (e.g. INT-001,INT-003).",
    )
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="LLM model for generating replacements.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM replacement, use local extraction rules instead.",
    )
    return parser.parse_args()


def _validate_output_dir(output_dir: str) -> None:
    if output_dir:
        abs_output_dir = os.path.abspath(output_dir)
        norm_path = os.path.normpath(abs_output_dir)
        path_parts = norm_path.split(os.sep)
        is_source_path = False
        for i in range(len(path_parts) - 1):
            if (
                path_parts[i] == project_paths.DATA_DIR
                and path_parts[i + 1] == project_paths.SOURCES_DIR
            ):
                is_source_path = True
                break
        if is_source_path:
            logger.error(
                f"Writing to source files in {project_paths.DATA_SOURCES_DIR}/ is strictly prohibited by AI guardrails."
            )
            sys.exit(1)

    if not os.path.exists(output_dir):
        logger.error(f"Directory '{output_dir}' does not exist.")
        sys.exit(1)


def _load_inputs(output_dir: str) -> tuple[str, str, list[str], list[dict], str]:
    basename = os.path.basename(os.path.abspath(output_dir))
    formatted_txt_path = project_paths.resolve_formatted_draft_path(
        output_dir, basename
    )
    findings_yaml_path = project_paths.resolve_findings_yaml_path(output_dir, basename)

    if not os.path.exists(formatted_txt_path):
        logger.error(f"'{formatted_txt_path}' not found.")
        sys.exit(1)
    if not os.path.exists(findings_yaml_path):
        logger.error(f"'{findings_yaml_path}' not found.")
        sys.exit(1)

    raw_text = read_file(formatted_txt_path)
    text_lines = raw_text.splitlines(keepends=True)

    try:
        yaml_data = YamlHandler.load(findings_yaml_path)
        findings = yaml_data.get("findings", []) if isinstance(yaml_data, dict) else []
    except Exception as e:
        logger.error(f"Error parsing YAML '{findings_yaml_path}': {e}", exc_info=True)
        sys.exit(1)

    return formatted_txt_path, findings_yaml_path, text_lines, findings, basename


def main():
    args = _parse_args()

    logger.info(f"Starting apply_findings for directory: {args.dir}")
    _validate_output_dir(args.dir)

    formatted_txt_path, findings_yaml_path, text_lines, findings, basename = (
        _load_inputs(args.dir)
    )

    if not findings:
        logger.info("No findings to apply.")
        sys.exit(0)

    if not args.interactive and not args.accept_ids and not args.auto:
        logger.warning("No mode specified. Defaulting to interactive mode.")
        args.interactive = True

    active_findings = _determine_accepted_findings(findings, text_lines, args)
    logger.info(f"Determined {len(active_findings)} active findings to apply.")

    groups = _group_findings(active_findings)
    logger.info(f"Grouped active findings into {len(groups)} blocks.")

    applied_count, failed_count = _apply_grouped_findings(text_lines, groups, args)

    if failed_count > 0:
        logger.error(
            f"安全対策ガードレール: {failed_count} 件の指摘の反映に失敗しました。"
            "小説テキストおよびYAMLファイルの変更を保存せず、元の状態を維持して処理を中断します。"
        )
        sys.exit(1)

    skipped_count = sum(1 for f in findings if f.get("accepted") != "y")
    stats = (applied_count, skipped_count, failed_count)

    _save_outputs_and_print_summary(
        formatted_txt_path, findings_yaml_path, text_lines, findings, stats
    )
    logger.info(
        f"Completed apply_findings. Stats: Applied={applied_count}, Skipped={skipped_count}, Failed={failed_count}"
    )


if __name__ == "__main__":
    main()
