import argparse
import os
import re
import sys

import yaml

from src.utils import project_paths
from src.utils.ai_client import AgyClientError
from src.utils.ai_task import BlockReplacementInput, BlockReplacementTask
from src.utils.file_io import read_file


def write_file(filepath, content):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def parse_line_number(location_str):
    """
    Parses line number from location string like "8行目" or "15".
    Returns 1-based index or None.
    """
    if not location_str:
        return None
    match = re.search(r"(\d+)", str(location_str))
    if match:
        return int(match.group(1))
    return None


def extract_suggestion_candidate(suggestion):
    """
    Attempts to extract a replacement candidate enclosed in quotes from the suggestion.
    e.g., 「修正後のテキスト」 or （例：「〜」）
    """
    # Look for text inside Japanese quotes 「...」
    matches = re.findall(r"「([^」]+)」", suggestion)
    if matches:
        # If there are multiple, prefer the longer one or the last one if it looks like a full sentence.
        # But generally, if there is at least one, we can return it as a candidate.
        return matches[-1]  # Usually the example is at the end
    return None


def find_target_line(text_lines, finding):
    """
    Finds the 1-based line number in text_lines where finding's original text exists.
    Looks near specified location first, then falls back to full scan.
    Returns 1-based index or None.
    """
    original = finding.get("original", "").strip().replace("\r\n", "\n")
    if not original:
        return None

    # Check using full text (normalising newlines)
    raw_text = "".join(text_lines).replace("\r\n", "\n")
    if original in raw_text:
        offset = raw_text.find(original)
        line_no = raw_text[:offset].count("\n") + 1
        return line_no

    location_str = finding.get("location", "")
    line_no = parse_line_number(location_str)

    if line_no is not None:
        target_idx = line_no - 1
        for idx in range(target_idx - 5, target_idx + 6):
            if 0 <= idx < len(text_lines):
                normalized_line = text_lines[idx].replace("\r\n", "\n").strip()
                if original in normalized_line:
                    return idx + 1

    for idx, line in enumerate(text_lines):
        normalized_line = line.replace("\r\n", "\n").strip()
        if original in normalized_line:
            return idx + 1

    # Fuzzy match: ignore all whitespace/newlines (normalise completely)
    import re

    def clean_spacing(text):
        return re.sub(r"\s+", "", text)

    clean_original = clean_spacing(original)
    if clean_original:
        clean_raw = clean_spacing(raw_text)
        if clean_original in clean_raw:
            start_char_idx = clean_raw.find(clean_original)
            char_count = 0
            for idx, line in enumerate(text_lines):
                char_count += len(clean_spacing(line))
                if char_count > start_char_idx:
                    return idx + 1

    return None


def apply_fallback_to_block(context_lines, findings_in_block):
    """
    Fallback replacement logic when LLM is unavailable.
    Replaces originals with extracted suggestions inside context_lines.
    Returns (modified_block_text, success_findings, failed_findings)
    """
    modified_block_text = "".join(context_lines)
    success_findings = []
    failed_findings = []

    for f in findings_in_block:
        original = f.get("original", "").strip()
        suggestion = f.get("suggestion", "").strip()
        replacement = extract_suggestion_candidate(suggestion)

        if not replacement:
            failed_findings.append(
                (
                    f,
                    "Could not extract replacement text from suggestion. Manual intervention required.",
                )
            )
            continue

        if original in modified_block_text:
            # We replace only the first occurrence to avoid messing up other parts of the block
            modified_block_text = modified_block_text.replace(original, replacement, 1)
            success_findings.append((f, replacement, "extracted"))
        else:
            failed_findings.append((f, f"Could not find original text: '{original}'"))

    return modified_block_text, success_findings, failed_findings


def query_llm_for_block_replacement(context_lines, findings_in_block, model):
    """
    Uses BlockReplacementTask to generate the rewritten block based on context and multiple findings.
    """
    task = BlockReplacementTask(model=model)
    input_data = BlockReplacementInput(
        context_lines=context_lines, findings_in_block=findings_in_block
    )
    try:
        result = task.execute(input_data)
        if result is None:
            print(
                "Warning: LLM output was rejected (too short or failed validation).",
                file=sys.stderr,
            )
        return result
    except AgyClientError as e:
        print(f"Warning: AgyClient failed with error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Unexpected error calling AgyClient: {e}", file=sys.stderr)
        return None


def print_finding_diff(finding):
    """
    Prints a formatted summary of the finding.
    """
    print("-" * 60)
    print(f"ID      : {finding.get('id', 'N/A')}")
    print(f"場所    : {finding.get('location', 'N/A')}")
    print(
        f"カテゴリ: {finding.get('category', 'N/A')} (重要度: {finding.get('severity', 'N/A')})"
    )
    print(f"分析    : {finding.get('analysis', 'N/A')}")
    print(f"原文    : \033[31m{finding.get('original', 'N/A')}\033[0m")
    print(f"修正案  : \033[32m{finding.get('suggestion', 'N/A')}\033[0m")
    print("-" * 60)


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
            print(
                f"Error: Writing to source files in {project_paths.DATA_SOURCES_DIR}/ is strictly prohibited by AI guardrails.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not os.path.exists(output_dir):
        print(f"Error: Directory '{output_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)


def _load_inputs(output_dir: str) -> tuple[str, str, list[str], list[dict], str]:
    basename = os.path.basename(os.path.abspath(output_dir))
    formatted_txt_path = project_paths.resolve_formatted_draft_path(
        output_dir, basename
    )
    findings_yaml_path = project_paths.resolve_findings_yaml_path(output_dir, basename)

    if not os.path.exists(formatted_txt_path):
        print(f"Error: '{formatted_txt_path}' not found.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(findings_yaml_path):
        print(f"Error: '{findings_yaml_path}' not found.", file=sys.stderr)
        sys.exit(1)

    raw_text = read_file(formatted_txt_path)
    text_lines = raw_text.splitlines(keepends=True)

    try:
        with open(findings_yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        findings = yaml_data.get("findings", []) if isinstance(yaml_data, dict) else []
    except Exception as e:
        print(f"Error parsing YAML '{findings_yaml_path}': {e}", file=sys.stderr)
        sys.exit(1)

    return formatted_txt_path, findings_yaml_path, text_lines, findings, basename


def _interactive_choice(finding: dict) -> str:
    """
    Prompts the user for a single finding and sets its accepted state.
    """
    print_finding_diff(finding)
    candidate = extract_suggestion_candidate(finding.get("suggestion", ""))
    if candidate:
        print(f"(抽出された簡易修正案候補: 「{candidate}」)")

    choice = (
        input(
            "この指摘を適用しますか？ [y:はい / n:いいえ / e:手動入力 / a:以降すべて適用 / q:終了して適用開始]: "
        )
        .strip()
        .lower()
    )

    if choice == "y":
        finding["accepted"] = "y"
    elif choice == "e":
        custom_replacement = input(
            "適用する修正後のテキストを入力してください: "
        ).strip()
        finding["suggestion"] = f"「{custom_replacement}」に修正してください。"
        finding["accepted"] = "y"

    return choice


def _apply_all_remaining(
    findings: list[dict],
    start_idx: int,
    accepted_ids: set[str],
    args: argparse.Namespace,
) -> None:
    """
    Sets accepted status for all remaining findings.
    """
    for remain_f in findings[start_idx:]:
        remain_fid = remain_f.get("id")
        if args.accept_ids:
            remain_f["accepted"] = "y" if remain_fid in accepted_ids else "n"
        else:
            remain_f["accepted"] = "y"


def _determine_accepted_findings_auto(
    findings: list[dict], accepted_ids: set[str], args: argparse.Namespace
) -> None:
    """
    Sets accepted status automatically based on accept_ids or auto flags.
    """
    for f in findings:
        fid = f.get("id")
        if args.accept_ids:
            f["accepted"] = "y" if fid in accepted_ids else "n"
        elif args.auto:
            if f.get("accepted") != "y":
                f["accepted"] = "n"


def _determine_accepted_findings_interactive(
    findings: list[dict], accepted_ids: set[str], args: argparse.Namespace
) -> None:
    """
    Queries the user interactively for each finding's accepted state.
    """
    for i, finding in enumerate(findings):
        choice = _interactive_choice(finding)

        if choice == "a":
            finding["accepted"] = "y"
            _apply_all_remaining(findings, i + 1, accepted_ids, args)
            args.interactive = False
            args.auto = True
            break
        elif choice == "q":
            print("適用処理を終了し、これまでに確定した変更を適用します。")
            break
        elif choice not in ("y", "e"):
            finding["accepted"] = "n"


def _determine_accepted_findings(
    findings: list[dict], text_lines: list[str], args: argparse.Namespace
) -> list[tuple[int, dict]]:
    accepted_ids = set()
    if args.accept_ids:
        accepted_ids = {x.strip() for x in args.accept_ids.split(",")}

    for f in findings:
        if "accepted" not in f:
            f["accepted"] = None

    if args.accept_ids or args.auto:
        _determine_accepted_findings_auto(findings, accepted_ids, args)
    else:
        _determine_accepted_findings_interactive(findings, accepted_ids, args)

    active_findings = []
    for f in findings:
        fid = f.get("id")
        if f.get("accepted") == "y":
            line_no = find_target_line(text_lines, f)
            if line_no is not None:
                active_findings.append((line_no, f))
            else:
                print(
                    f"[FAIL] {fid} の適用に失敗しました: 原文が見つかりません。",
                    file=sys.stderr,
                )
                f["apply_status"] = "failed"
                f["apply_result"] = "原文が見つかりませんでした。"
        else:
            f["apply_status"] = None
            f["apply_result"] = None

    return active_findings


def _group_findings(
    active_findings: list[tuple[int, dict]],
) -> list[list[tuple[int, dict]]]:
    active_findings.sort(key=lambda x: x[0])
    groups = []
    if active_findings:
        current_group = [active_findings[0]]
        for item in active_findings[1:]:
            last_line_no = current_group[-1][0]
            curr_line_no = item[0]
            if curr_line_no - last_line_no <= 5:
                current_group.append(item)
            else:
                groups.append(current_group)
                current_group = [item]
        groups.append(current_group)

    groups.sort(key=lambda g: g[0][0], reverse=True)
    return groups


def _apply_grouped_findings(
    text_lines: list[str],
    groups: list[list[tuple[int, dict]]],
    args: argparse.Namespace,
) -> tuple[int, int]:
    applied_count = 0
    failed_count = 0

    for group in groups:
        findings_in_block = [item[1] for item in group]
        line_nos = [item[0] for item in group]
        L_min = min(line_nos)
        L_max = max(line_nos)

        C = 4
        start_idx = max(0, L_min - 1 - C)
        end_idx = min(len(text_lines), L_max + C)
        context_lines = text_lines[start_idx:end_idx]

        success = False
        result_block_text = None

        if not args.no_llm:
            result_block_text = query_llm_for_block_replacement(
                context_lines, findings_in_block, args.model
            )
            if result_block_text:
                success = True

        if success and result_block_text:
            if not result_block_text.endswith("\n") and len(result_block_text) > 0:
                result_block_text += "\n"

            text_lines[start_idx:end_idx] = result_block_text.splitlines(keepends=True)

            for f in findings_in_block:
                fid = f.get("id")
                print(f"[SUCCESS] {fid} を適用しました (LLMコンテキスト一括方式)。")
                applied_count += 1
                f["apply_status"] = "success"
                f["apply_result"] = "LLMコンテキスト一括方式"
        else:
            result_block_text, success_findings, failed_findings = (
                apply_fallback_to_block(context_lines, findings_in_block)
            )
            if not result_block_text.endswith("\n") and len(result_block_text) > 0:
                result_block_text += "\n"

            text_lines[start_idx:end_idx] = result_block_text.splitlines(keepends=True)

            for f, replacement, m in success_findings:
                fid = f.get("id")
                print(f"[SUCCESS] {fid} を適用しました (フォールバック・{m}方式)。")
                print(f"  -> 置換後: '{replacement}'")
                applied_count += 1
                f["apply_status"] = "success"
                f["apply_result"] = f"フォールバック({m}方式): {replacement}"

            for f, error_msg in failed_findings:
                fid = f.get("id")
                print(
                    f"[FAIL] {fid} の適用に失敗しました: {error_msg}", file=sys.stderr
                )
                failed_count += 1
                f["apply_status"] = "failed"
                f["apply_result"] = error_msg

    return applied_count, failed_count


def _save_outputs_and_print_summary(
    formatted_txt_path: str,
    findings_yaml_path: str,
    text_lines: list[str],
    findings: list[dict],
    stats: tuple[int, int, int],
) -> None:
    write_file(formatted_txt_path, "".join(text_lines))
    print(f"\n小説テキストを更新しました: {formatted_txt_path}")

    updated_yaml_data = {"findings": findings}
    try:
        with open(findings_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                updated_yaml_data, f, allow_unicode=True, default_flow_style=False
            )
        print(f"指摘YAMLを更新しました: {findings_yaml_path}")
    except Exception as e:
        print(f"Error saving updated YAML '{findings_yaml_path}': {e}", file=sys.stderr)

    applied_count, skipped_count, failed_count = stats
    print("\n=== 反映処理完了 ===")
    print(
        f"適用: {applied_count} 件, スキップ: {skipped_count} 件, 失敗: {failed_count} 件"
    )


def main():
    args = _parse_args()

    _validate_output_dir(args.dir)

    formatted_txt_path, findings_yaml_path, text_lines, findings, basename = (
        _load_inputs(args.dir)
    )

    if not findings:
        print("No findings to apply.")
        sys.exit(0)

    if not args.interactive and not args.accept_ids and not args.auto:
        print("Warning: No mode specified. Defaulting to interactive mode.")
        args.interactive = True

    active_findings = _determine_accepted_findings(findings, text_lines, args)

    groups = _group_findings(active_findings)

    applied_count, failed_count = _apply_grouped_findings(text_lines, groups, args)

    skipped_count = sum(1 for f in findings if f.get("accepted") != "y")
    stats = (applied_count, skipped_count, failed_count)

    _save_outputs_and_print_summary(
        formatted_txt_path, findings_yaml_path, text_lines, findings, stats
    )


if __name__ == "__main__":
    main()
