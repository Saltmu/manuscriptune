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
    original = finding.get("original", "").strip()
    if not original:
        return None

    location_str = finding.get("location", "")
    line_no = parse_line_number(location_str)

    if line_no is not None:
        target_idx = line_no - 1
        for idx in range(target_idx - 5, target_idx + 6):
            if 0 <= idx < len(text_lines):
                if original in text_lines[idx]:
                    return idx + 1

    for idx, line in enumerate(text_lines):
        if original in line:
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
    Uses the agy CLI to generate the rewritten block based on context and multiple findings.
    """
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
・出力するテキストブロックには、行番号（「1: 」など）や、解説、挨拶、マークダウンのコードブロック（```）などは一切含めないでください。純粋な小説の本文のみを出力してください。
・行数は元のテキストブロックとおおむね同程度とし、修正指示に関係のない部分は元の文章をそのまま維持してください。
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
        # Clean up markdown formatting
        result = re.sub(r"^```[a-zA-Z]*\n", "", result)
        result = re.sub(r"\n```$", "", result).strip()

        # Guard: if LLM output is too short (e.g. LLM failed and returned generic message or empty)
        original_length = sum(len(line) for line in context_lines)
        if len(result) < original_length * 0.3:
            print(
                f"Warning: LLM output is too short ({len(result)} vs original {original_length}). Rejecting output.",
                file=sys.stderr,
            )
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
    except FileNotFoundError:
        print(
            "Warning: 'agy' CLI not found. Cannot use LLM for replacement.",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(f"Warning: Unexpected error calling agy: {e}", file=sys.stderr)
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

    basename = os.path.basename(os.path.abspath(output_dir))
    formatted_txt_path = os.path.join(output_dir, f"{basename}_formatted.txt")
    findings_yaml_path = os.path.join(output_dir, f"{basename}_findings.yaml")

    # Fallback for backward compatibility
    if not os.path.exists(formatted_txt_path):
        fallback_txt = os.path.join(output_dir, "01_formatted.txt")
        if os.path.exists(fallback_txt):
            formatted_txt_path = fallback_txt

    if not os.path.exists(findings_yaml_path):
        fallback_yaml = os.path.join(output_dir, "00_integrated_findings.yaml")
        if os.path.exists(fallback_yaml):
            findings_yaml_path = fallback_yaml

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

    # Default to interactive mode if no mode is specified
    if not args.interactive and not args.accept_ids and not args.auto:
        print("Warning: No mode specified. Defaulting to interactive mode.")
        args.interactive = True

    # Filter/Select findings to apply
    accepted_ids = set()
    if args.accept_ids:
        accepted_ids = {x.strip() for x in args.accept_ids.split(",")}

    # Initialize/normalize accepted status in YAML findings
    for f in findings:
        if "accepted" not in f:
            f["accepted"] = None

    # Phase 1: Determine which findings to apply (User input / CLI parameters)
    for i, finding in enumerate(findings):
        fid = finding.get("id")

        if args.accept_ids:
            if fid in accepted_ids:
                finding["accepted"] = "y"
            else:
                finding["accepted"] = "n"
            continue

        if args.auto:
            if finding.get("accepted") != "y":
                finding["accepted"] = "n"
            continue

        # Interactive Mode
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
        elif choice == "a":
            finding["accepted"] = "y"
            for remain_f in findings[i + 1 :]:
                remain_fid = remain_f.get("id")
                if args.accept_ids:
                    if remain_fid in accepted_ids:
                        remain_f["accepted"] = "y"
                    else:
                        remain_f["accepted"] = "n"
                else:
                    remain_f["accepted"] = "y"
            args.interactive = False
            args.auto = True
            break
        elif choice == "q":
            print("適用処理を終了し、これまでに確定した変更を適用します。")
            break
        else:
            finding["accepted"] = "n"

    # Phase 2: Grouping and Application
    active_findings = []
    skipped_count = 0

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
            skipped_count += 1
            f["apply_status"] = None
            f["apply_result"] = None

    # Group close findings (within 5 lines of each other)
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

    # Sort groups in descending order of line numbers to apply from bottom to top
    groups.sort(key=lambda g: g[0][0], reverse=True)

    applied_count = 0
    failed_count = 0

    for group in groups:
        findings_in_block = [item[1] for item in group]
        line_nos = [item[0] for item in group]
        L_min = min(line_nos)
        L_max = max(line_nos)

        C = 4  # Context size
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
            # Fallback
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

    # Save modified text
    write_file(formatted_txt_path, "".join(text_lines))
    print(f"\n小説テキストを更新しました: {formatted_txt_path}")

    # Save updated findings YAML
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
