import argparse
import os
import re
import subprocess
import sys

import yaml


def read_file(filepath):
    if not filepath or not os.path.exists(filepath):
        return ""
    with open(filepath, encoding="utf-8") as f:
        return f.read()


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


def query_llm_for_replacement(original, suggestion, model):
    """
    Uses the agy CLI to generate the rewritten text based on original text and suggestion.
    """
    prompt = f"""あなたは小説の優秀な編集者です。
以下の【修正対象の原文】を、【修正の提案・解説】に従って適切に書き換えてください。

【修正対象の原文】
{original}

【修正の提案・解説】
{suggestion}

【出力ルール】
・修正・書き換え後のテキストのみを出力してください。
・解説、挨拶、マークダウンのコードブロック（```）などは一切出力しないでください。
・原文の意味やニュアンスを保ちつつ、指摘された問題点（語彙、設定矛盾、表現など）のみを解消してください。
"""

    cmd = ["agy", "-p", "", "--model", model]
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(input=prompt)

        if process.returncode != 0:
            print(
                f"Warning: agy CLI failed with error: {stderr.strip()}", file=sys.stderr
            )
            return None

        result = stdout.strip()
        # Clean up any accidental markdown formatting the LLM might have returned
        result = re.sub(r"^```[a-zA-Z]*\n", "", result)
        result = re.sub(r"\n```$", "", result).strip()
        return result
    except FileNotFoundError:
        print(
            "Warning: 'agy' CLI not found. Cannot use LLM for replacement.",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(f"Warning: Unexpected error calling agy: {e}", file=sys.stderr)
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


def apply_finding_to_text(text_lines, finding, model, use_llm=True):
    """
    Applies a single finding to the list of text lines.
    Modifies text_lines in place if match is found.
    Returns (success, applied_text, method)
    """
    original = finding.get("original", "").strip()
    suggestion = finding.get("suggestion", "").strip()
    location_str = finding.get("location", "")

    if not original:
        return False, "Original text is empty", None

    line_no = parse_line_number(location_str)

    # Define a helper to replace within a range of lines
    def try_replace_in_range(start_idx, end_idx):
        for idx in range(start_idx, end_idx):
            if idx < 0 or idx >= len(text_lines):
                continue
            line = text_lines[idx]
            if original in line:
                return idx, line
        return None, None

    match_idx = None
    matched_line = None

    if line_no is not None:
        # Try near the specified line (1-based index converted to 0-based index)
        target_idx = line_no - 1
        # Look in range [target_idx - 5, target_idx + 5]
        match_idx, matched_line = try_replace_in_range(target_idx - 5, target_idx + 6)

    if match_idx is None:
        # Fallback: scan the entire file
        match_idx, matched_line = try_replace_in_range(0, len(text_lines))

    if match_idx is None:
        return False, f"Could not find original text: '{original}'", None

    # Determine replacement content
    replacement = None
    method = "direct"

    # Try LLM first if enabled
    if use_llm:
        replacement = query_llm_for_replacement(original, suggestion, model)
        if replacement:
            method = "llm"

    # Fallback to extraction from suggestion if LLM failed or disabled
    if not replacement:
        extracted = extract_suggestion_candidate(suggestion)
        if extracted:
            replacement = extracted
            method = "extracted"

    # Absolute fallback: if no candidate could be extracted, we cannot perform automatic replacement
    if not replacement:
        return (
            False,
            "Could not extract replacement text from suggestion. Manual intervention required.",
            None,
        )

    # Execute the replacement in the line
    new_line = matched_line.replace(original, replacement)
    text_lines[match_idx] = new_line

    return True, replacement, method


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


def main():
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
    args = parser.parse_args()

    output_dir = args.dir
    if not os.path.exists(output_dir):
        print(f"Error: Directory '{output_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    formatted_txt_path = os.path.join(output_dir, "01_formatted.txt")
    findings_yaml_path = os.path.join(output_dir, "00_integrated_findings.yaml")

    if not os.path.exists(formatted_txt_path):
        print(f"Error: '{formatted_txt_path}' not found.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(findings_yaml_path):
        print(f"Error: '{findings_yaml_path}' not found.", file=sys.stderr)
        sys.exit(1)

    # Read formatted text (split into lines)
    raw_text = read_file(formatted_txt_path)
    text_lines = raw_text.splitlines(keepends=True)

    # Load findings YAML
    try:
        with open(findings_yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        findings = yaml_data.get("findings", []) if isinstance(yaml_data, dict) else []
    except Exception as e:
        print(f"Error parsing YAML '{findings_yaml_path}': {e}", file=sys.stderr)
        sys.exit(1)

    if not findings:
        print("No findings to apply.")
        sys.exit(0)

    # Filter/Select findings to apply
    accepted_ids = set()
    if args.accept_ids:
        accepted_ids = {x.strip() for x in args.accept_ids.split(",")}

    # Sort findings by line number in descending order (reverse application)
    # This prevents line number shifts from affecting upper lines.
    def get_sort_key(f):
        ln = parse_line_number(f.get("location", ""))
        return ln if ln is not None else 0

    findings_sorted = sorted(findings, key=get_sort_key, reverse=True)

    applied_count = 0
    skipped_count = 0
    failed_count = 0

    findings_map = {f.get("id"): f for f in findings}

    for finding in findings_sorted:
        fid = finding.get("id")

        # Determine if we should apply this finding
        should_apply = False

        if args.interactive:
            print_finding_diff(finding)
            # Suggest extracted replacement if LLM disabled or for review
            candidate = extract_suggestion_candidate(finding.get("suggestion", ""))
            if candidate:
                print(f"(抽出された簡易修正案候補: 「{candidate}」)")

            choice = (
                input(
                    "この指摘を適用しますか？ [y:はい / n:いいえ / e:手動入力 / a:以降すべて適用 / q:終了して保存]: "
                )
                .strip()
                .lower()
            )
            if choice == "y":
                should_apply = True
            elif choice == "e":
                custom_replacement = input(
                    "適用する修正後のテキストを入力してください: "
                ).strip()
                # Override suggestion for this run
                finding["suggestion"] = f"「{custom_replacement}」に修正してください。"
                should_apply = True
            elif choice == "a":
                args.interactive = False
                args.auto = True
                # Also mark current and subsequent accepted ones
                should_apply = True
            elif choice == "q":
                print("適用処理を終了し、これまでの変更を保存します。")
                break
            else:
                # 'n' or anything else
                skipped_count += 1
                finding["accepted"] = "n"
                continue
        elif args.accept_ids:
            if fid in accepted_ids:
                should_apply = True
            else:
                skipped_count += 1
                continue
        elif args.auto:
            if finding.get("accepted") == "y":
                should_apply = True
            else:
                skipped_count += 1
                continue
        else:
            # If no mode selected, default to interactive
            print("Warning: No mode specified. Defaulting to interactive mode.")
            args.interactive = True
            # Re-run loop for this finding
            print_finding_diff(finding)
            choice = input("この指摘を適用しますか？ [y/n/e/a/q]: ").strip().lower()
            if choice == "y":
                should_apply = True
            elif choice == "e":
                custom_replacement = input(
                    "修正後のテキストを入力してください: "
                ).strip()
                finding["suggestion"] = f"「{custom_replacement}」に修正してください。"
                should_apply = True
            elif choice == "a":
                args.interactive = False
                args.auto = True
                should_apply = True
            elif choice == "q":
                break
            else:
                skipped_count += 1
                finding["accepted"] = "n"
                continue

        if should_apply:
            # Apply the finding
            success, result_text, method = apply_finding_to_text(
                text_lines, finding, args.model, not args.no_llm
            )
            if success:
                print(f"[SUCCESS] {fid} を適用しました ({method}方式)。")
                print(f"  -> 置換後: '{result_text}'")
                applied_count += 1
                # Update status in original list
                if fid in findings_map:
                    findings_map[fid]["accepted"] = "y"
            else:
                print(
                    f"[FAIL] {fid} の適用に失敗しました: {result_text}", file=sys.stderr
                )
                failed_count += 1
                if fid in findings_map:
                    findings_map[fid]["accepted"] = "n"

    # Save modified text
    write_file(formatted_txt_path, "".join(text_lines))
    print(f"\n小説テキストを更新しました: {formatted_txt_path}")

    # Save updated findings YAML
    # Keep original order when saving YAML
    updated_yaml_data = {"findings": findings}
    try:
        with open(findings_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                updated_yaml_data, f, allow_unicode=True, default_flow_style=False
            )
        print(f"指摘YAMLを更新しました: {findings_yaml_path}")
    except Exception as e:
        print(f"Error saving updated YAML '{findings_yaml_path}': {e}", file=sys.stderr)

    print("\n=== 反映処理完了 ===")
    print(
        f"適用: {applied_count} 件, スキップ: {skipped_count} 件, 失敗: {failed_count} 件"
    )


if __name__ == "__main__":
    main()
