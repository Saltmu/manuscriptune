import argparse
import os
import sys

from src.findings import integration as _integration
from src.findings.integration import BaseFindingsIntegrator, IntegrationContext
from src.utils import project_paths
from src.utils.ai_task import FindingsIntegrationInput, FindingsIntegrationTask
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)

parse_yaml_file = _integration.parse_yaml_file

_SEVERITY_TITLES = {
    "high": "重大な課題",
    "medium": "中程度の改善提案",
    "low": "軽微な指摘",
    "info": "参考情報",
}


def generate_markdown_report(findings, output_md):
    """
    Generates a human-readable markdown summary report from the integrated findings.
    """
    return _integration.generate_markdown_report(
        findings,
        output_md,
        report_title="# 小説校閲 統合レポート",
        no_findings_message="指摘事項はありませんでした。ロジック・表現ともに非常に良好です。",
        summary_message='合計 {count} 件の指摘が統合・整理されました。各指摘を確認し、YAMLファイル上で `accepted: "y"` に変更して反映してください。',
        severity_titles=_SEVERITY_TITLES,
        item_label="対象テキスト",
        suggestion_label="修正提案",
        default_id_prefix="INT",
    )


def run_integration_llm(output_dir, target_text, raw_findings_text, model):
    """
    Calls FindingsIntegrationTask to merge and resolve conflicts in the findings.
    """
    return _integration.run_integration_llm(
        target_text,
        raw_findings_text,
        model,
        task_cls=FindingsIntegrationTask,
        input_cls=FindingsIntegrationInput,
        log_prefix="consolidation",
    )


def _collect_raw_findings(output_dir: str) -> list[dict]:
    """
    Locates and parses all finding YAML files in the given directory.

    YAML files matching the pattern ``[0-9][0-9]_*.yaml`` (with a numeric prefix
    of 02 or greater) are detected dynamically via directory scan so that adding a
    new review skill requires no manual update here.
    """
    import glob

    # Discover all numbered skill YAML files (e.g. 02_logic_consistency.yaml)
    # sorted by filename so they are processed in a consistent order.
    pattern = os.path.join(output_dir, "[0-9][0-9]_*.yaml")
    yaml_files = sorted(
        p
        for p in glob.glob(pattern)
        # Skip the filtered context file prefix which is not a findings YAML
        if not os.path.basename(p).startswith(
            project_paths.FILTERED_CONTEXT_NAME.split("_")[0] + "_"
        )
    )

    logger.info(f"Found {len(yaml_files)} YAML files to integrate.")

    all_findings = []
    for yf in yaml_files:
        filename = os.path.basename(yf)
        findings = parse_yaml_file(yf)
        logger.info(f"  - {filename}: {len(findings)} findings")
        for f in findings:
            f["_source_file"] = filename
            all_findings.append(f)

    return all_findings


def _fallback_merge(all_findings: list[dict]) -> str:
    """
    Performs mechanical fallback merging when LLM is unavailable.
    """
    return _integration.fallback_merge(
        all_findings,
        id_prefix="INT",
        extra_metadata={
            "fallback_mode": True,
            "reason": "LLM integration failed; using mechanical merge",
            "completeness": "low",
        },
    )


class TextFindingsIntegrator(BaseFindingsIntegrator):
    """Findings integrator for novel text review (see BaseFindingsIntegrator)."""

    def _collect_raw_findings(self, output_dir):
        return _collect_raw_findings(output_dir)

    def _prepare(self, output_dir, **kwargs):
        basename = os.path.basename(os.path.abspath(output_dir))
        formatted_txt_path = project_paths.resolve_formatted_draft_path(
            output_dir, basename
        )
        if not os.path.exists(formatted_txt_path):
            logger.error(f"'{basename}_formatted.txt' not found in {output_dir}.")
            return None
        return IntegrationContext(
            target_text=read_file(formatted_txt_path),
            yaml_path=project_paths.get_findings_yaml_path(output_dir, basename),
            report_path=project_paths.get_report_md_path(output_dir, basename),
        )

    def _run_integration_llm(self, output_dir, target_text, raw_findings_text):
        return run_integration_llm(
            output_dir, target_text, raw_findings_text, self.model
        )

    def _fallback_merge(self, all_findings):
        return _fallback_merge(all_findings)

    def _generate_markdown_report(self, findings, output_md):
        generate_markdown_report(findings, output_md)


def integrate_findings_in_dir(output_dir, model):
    """
    Integrates and resolves conflicts in parallel review findings.
    Returns True on success, False on failure.
    """
    return TextFindingsIntegrator(model).run(output_dir)


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
