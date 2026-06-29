import argparse
import os
import sys

from src.utils import project_paths
from src.utils.ai_client import AgyClientError
from src.utils.ai_task import FindingsIntegrationInput, FindingsIntegrationTask
from src.utils.file_io import read_file
from src.utils.yaml_handler import YamlHandler


def parse_yaml_file(filepath):
    return YamlHandler.load_findings(filepath)


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
    Calls FindingsIntegrationTask to merge and resolve conflicts in the findings.
    """
    print(f"Sending consolidation request to AgyClient ({model})...")
    task = FindingsIntegrationTask(model=model)
    input_data = FindingsIntegrationInput(
        target_text=target_text, raw_findings_text=raw_findings_text
    )
    try:
        return task.execute(input_data)
    except AgyClientError as e:
        print(f"Error calling AgyClient: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unexpected error calling AgyClient: {e}", file=sys.stderr)
        return None


def _collect_raw_findings(output_dir: str) -> list[dict]:
    """
    Locates and parses all finding YAML files in the given directory.
    """
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

    print(f"Found {len(yaml_files)} YAML files to integrate.")

    all_findings = []
    for yf in yaml_files:
        filename = os.path.basename(yf)
        findings = parse_yaml_file(yf)
        print(f"  - {filename}: {len(findings)} findings")
        for f in findings:
            f["_source_file"] = filename
            all_findings.append(f)

    return all_findings


def _fallback_merge(all_findings: list[dict]) -> str:
    """
    Performs mechanical fallback merging when LLM is unavailable.
    """
    merged_findings = []
    for idx, f in enumerate(all_findings, 1):
        f_copy = f.copy()
        f_copy["id"] = f"INT-{idx:03d}"
        if "_source_file" in f_copy:
            del f_copy["_source_file"]
        merged_findings.append(f_copy)
    return YamlHandler.dump({"findings": merged_findings})


def integrate_findings_in_dir(output_dir, model):
    """
    Integrates and resolves conflicts in parallel review findings.
    Returns True on success, False on failure.
    """
    if not os.path.exists(output_dir):
        print(f"Error: Directory '{output_dir}' does not exist.", file=sys.stderr)
        return False

    basename = os.path.basename(os.path.abspath(output_dir))
    formatted_txt_path = project_paths.resolve_formatted_draft_path(
        output_dir, basename
    )
    if not os.path.exists(formatted_txt_path):
        print(
            f"Error: '{basename}_formatted.txt' not found in {output_dir}.",
            file=sys.stderr,
        )
        return False

    target_text = read_file(formatted_txt_path)

    # Collect findings
    all_findings = _collect_raw_findings(output_dir)

    if not all_findings:
        print("No findings to merge. Writing empty integrated findings.")
        integrated_yaml_path = project_paths.get_findings_yaml_path(
            output_dir, basename
        )
        with open(integrated_yaml_path, "w", encoding="utf-8") as f:
            f.write("findings: []\n")
        generate_markdown_report(
            [], project_paths.get_report_md_path(output_dir, basename)
        )
        print("Done.")
        return True

    raw_findings_text = YamlHandler.dump({"findings": all_findings})

    # Run integration via LLM
    merged_yaml_content = run_integration_llm(
        output_dir, target_text, raw_findings_text, model
    )

    if not merged_yaml_content:
        print("Error: LLM integration failed. Performing mechanical fallback merging.")
        merged_yaml_content = _fallback_merge(all_findings)

    # Write output
    integrated_yaml_path = project_paths.get_findings_yaml_path(output_dir, basename)
    with open(integrated_yaml_path, "w", encoding="utf-8") as f:
        f.write(merged_yaml_content + "\n")
    print(f"Saved integrated findings to {integrated_yaml_path}")

    # Parse back the merged findings to generate Markdown report
    try:
        merged_findings_list = YamlHandler.load_findings(merged_yaml_content)
    except Exception:
        merged_findings_list = []
        print(
            "Warning: Could not parse merged YAML back for Markdown report generation."
        )

    report_md_path = project_paths.get_report_md_path(output_dir, basename)
    generate_markdown_report(merged_findings_list, report_md_path)
    print(f"Saved Markdown report to {report_md_path}")
    return True


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

    success = integrate_findings_in_dir(args.dir, args.model)
    if not success:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
