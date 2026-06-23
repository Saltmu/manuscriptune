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


def parse_yaml_file(filepath):
    content = read_file(filepath)
    if not content:
        return []
    try:
        # Some YAML might have formatting issues, try sanitizing code blocks first
        sanitized = re.sub(r"```yaml\s*([\s\S]*?)```", r"\1", content).strip()
        data = yaml.safe_load(sanitized)
        if isinstance(data, dict) and "findings" in data:
            return data["findings"]
        elif isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Maybe the top-level has other keys
            for k, v in data.items():
                if isinstance(v, list):
                    return v
    except Exception as e:
        print(f"Warning: Failed to parse YAML file '{filepath}': {e}", file=sys.stderr)
    return []


def generate_markdown_report(findings, output_md):
    """
    Generates a human-readable markdown summary report from the integrated findings.
    """
    md = "# 小説校閲 統合レポート\n\n"
    if not findings:
        md += "指摘事項はありませんでした。ロジック・表現ともに非常に良好です。\n"
    else:
        md += f'合計 {len(findings)} 件の指摘が統合・整理されました。各指摘を確認し、YAMLファイル上で `accepted: "y"` に変更して反映してください。\n\n'

        # Categorize by severity
        severities = {"high": [], "medium": [], "low": [], "info": []}
        for f in findings:
            sev = f.get("severity", "low").lower()
            if sev in severities:
                severities[sev].append(f)
            else:
                severities["low"].append(f)

        for sev_level in ["high", "medium", "low", "info"]:
            level_findings = severities[sev_level]
            if not level_findings:
                continue

            emoji = {"high": "🚨", "medium": "⚠️", "low": "💡", "info": "ℹ️"}[sev_level]
            title = {
                "high": "重大な課題",
                "medium": "中程度の改善提案",
                "low": "軽微な指摘",
                "info": "参考情報",
            }[sev_level]

            md += f"## {emoji} {title} ({len(level_findings)}件)\n\n"

            for item in level_findings:
                md += f"### [{item.get('id', 'INT')}] {item.get('category', '指摘')} (場所: {item.get('location', '不明')})\n"
                md += f"- **対象テキスト:** `{item.get('original', '')}`\n"
                md += f"- **分析:** {item.get('analysis', '')}\n"
                md += f"- **修正提案:** {item.get('suggestion', '')}\n\n"

    with open(output_md, "w", encoding="utf-8") as f:
        f.write(md)


def run_integration_llm(output_dir, target_text, raw_findings_text, model):
    """
    Calls the agy CLI to merge and resolve conflicts in the findings.
    """
    prompt = f"""あなたは小説の編集長です。
以下は、異なる専門性を持つ校閲エージェントから提出された、同一の小説章に対する校閲指摘（YAML形式）のリストです。

【校閲対象の小説テキスト】
==============================
{target_text}
==============================

【検出された校閲指摘リスト】
==============================
{raw_findings_text}
==============================

上記の指摘リストを精査し、以下のルールに従って1つの統合された指摘リスト（YAML）を作成してください。

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
     - `original` (該当箇所のテキスト抜粋)
     - `category` (カテゴリ名)
     - `severity` (high / medium / low / info)
     - `analysis` (統合・競合解決された分析内容)
     - `suggestion` (統合・調整された修正案)
     - `accepted` ("n" で固定)

もし指摘事項がなくなった場合は、以下のように空のfindingsリストを出力してください。
```yaml
findings: []
```
"""

    print(f"Sending consolidation request to agy CLI ({model})...")
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
            print(f"Error calling agy: {stderr}", file=sys.stderr)
            return None

        result_text = stdout.strip()
        yaml_match = re.search(r"```yaml\s*([\s\S]*?)```", result_text)
        if yaml_match:
            return yaml_match.group(1).strip()
        return result_text
    except FileNotFoundError:
        print("Error: 'agy' CLI is not installed or not in PATH.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unexpected error calling agy: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Integrate and resolve conflicts in parallel review findings."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory containing the review output YAML files.",
    )
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="AI Model to use for the merging process.",
    )
    args = parser.parse_args()

    output_dir = args.dir
    if not os.path.exists(output_dir):
        print(f"Error: Directory '{output_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    formatted_txt_path = os.path.join(output_dir, "01_formatted.txt")
    if not os.path.exists(formatted_txt_path):
        print(f"Error: '01_formatted.txt' not found in {output_dir}.", file=sys.stderr)
        sys.exit(1)

    target_text = read_file(formatted_txt_path)

    # Locate all finding YAML files
    yaml_files = []
    # 1. Check for integrated pipeline YAMLs
    integrated_yamls = ["02_logic_consistency.yaml", "03_style_expression.yaml"]
    for yf in integrated_yamls:
        path = os.path.join(output_dir, yf)
        if os.path.exists(path):
            yaml_files.append(path)

    # 2. Check for individual skill YAMLs (fallback / python pipeline)
    if not yaml_files:
        individual_yamls = [
            "02_world_logic.yaml",
            "03_consistency.yaml",
            "04_show_dont_tell.yaml",
            "05_foreshadowing.yaml",
            "06_pacing.yaml",
            "07_rhythm.yaml",
            "08_character_voice.yaml",
        ]
        for yf in individual_yamls:
            path = os.path.join(output_dir, yf)
            if os.path.exists(path):
                yaml_files.append(path)

    if not yaml_files:
        print("No finding YAML files found to integrate.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(yaml_files)} YAML files to integrate.")

    all_findings = []
    for yf in yaml_files:
        filename = os.path.basename(yf)
        findings = parse_yaml_file(yf)
        print(f"  - {filename}: {len(findings)} findings")
        for f in findings:
            # Tag the source file in description for reference
            f["_source_file"] = filename
            all_findings.append(f)

    if not all_findings:
        print("No findings to merge. Writing empty integrated findings.")
        integrated_yaml_path = os.path.join(output_dir, "00_integrated_findings.yaml")
        with open(integrated_yaml_path, "w", encoding="utf-8") as f:
            f.write("findings: []\n")
        generate_markdown_report(
            [], os.path.join(output_dir, "00_integrated_report.md")
        )
        print("Done.")
        sys.exit(0)

    # Serialize all findings into a structured format for LLM input
    raw_findings_text = yaml.dump(
        {"findings": all_findings}, allow_unicode=True, default_flow_style=False
    )

    # Run integration via LLM
    merged_yaml_content = run_integration_llm(
        output_dir, target_text, raw_findings_text, args.model
    )

    if not merged_yaml_content:
        print("Error: LLM integration failed. Performing mechanical fallback merging.")
        # Simple mechanical merge without LLM (no conflict resolution)
        merged_findings = []
        for idx, f in enumerate(all_findings, 1):
            f_copy = f.copy()
            f_copy["id"] = f"INT-{idx:03d}"
            # Remove helper key
            if "_source_file" in f_copy:
                del f_copy["_source_file"]
            merged_findings.append(f_copy)
        merged_yaml_content = yaml.dump(
            {"findings": merged_findings}, allow_unicode=True, default_flow_style=False
        )

    # Write output
    integrated_yaml_path = os.path.join(output_dir, "00_integrated_findings.yaml")
    with open(integrated_yaml_path, "w", encoding="utf-8") as f:
        f.write(merged_yaml_content + "\n")
    print(f"Saved integrated findings to {integrated_yaml_path}")

    # Parse back the merged findings to generate Markdown report
    try:
        parsed_merged = yaml.safe_load(merged_yaml_content)
        merged_findings_list = (
            parsed_merged.get("findings", []) if isinstance(parsed_merged, dict) else []
        )
    except Exception:
        merged_findings_list = []
        print(
            "Warning: Could not parse merged YAML back for Markdown report generation."
        )

    report_md_path = os.path.join(output_dir, "00_integrated_report.md")
    generate_markdown_report(merged_findings_list, report_md_path)
    print(f"Saved Markdown report to {report_md_path}")


if __name__ == "__main__":
    main()
