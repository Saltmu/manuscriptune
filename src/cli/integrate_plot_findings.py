import argparse
import os
import sys

from src.findings import integration as _integration
from src.findings.integration import BaseFindingsIntegrator, IntegrationContext
from src.utils import project_paths
from src.utils.ai_task import PlotFindingsIntegrationInput, PlotFindingsIntegrationTask
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)

parse_yaml_file = _integration.parse_yaml_file

_SEVERITY_TITLES = {
    "high": "重大な課題 (GMCO欠如・深刻な中だるみ等)",
    "medium": "構成改善の提案 (動機づけ・山場補強等)",
    "low": "軽微な指摘",
    "info": "参考情報",
}


def generate_markdown_report(findings, output_md):
    """Generates a human-readable markdown summary report from the integrated plot findings."""
    return _integration.generate_markdown_report(
        findings,
        output_md,
        report_title="# プロット構成校閲 統合レポート",
        no_findings_message="指摘事項はありませんでした。プロット構成は非常に良好です。",
        summary_message="合計 {count} 件の指摘が統合・整理されました。各指摘を確認し、プロットのブラッシュアップに役立ててください。",
        severity_titles=_SEVERITY_TITLES,
        item_label="対象プロット記述",
        suggestion_label="構成改善案",
        default_id_prefix="PINT",
    )


def run_integration_llm(output_dir, target_text, raw_findings_text, model):
    logger.info(f"Sending plot consolidation request to AgyClient ({model})...")
    return _integration.run_integration_llm(
        target_text,
        raw_findings_text,
        model,
        task_cls=PlotFindingsIntegrationTask,
        input_cls=PlotFindingsIntegrationInput,
        log_prefix="plot consolidation",
    )


def _collect_raw_findings(output_dir: str) -> list[dict]:
    """Locates and parses all plot finding YAML files in the given directory."""
    yaml_files = []
    integrated_yamls = list(project_paths.PLOT_REVIEW_SKILLS.values())
    for yf in integrated_yamls:
        path = os.path.join(output_dir, yf)
        if os.path.exists(path):
            yaml_files.append(path)

    logger.info(f"Found {len(yaml_files)} plot YAML files to integrate.")

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
    """Performs mechanical fallback merging when LLM is unavailable."""
    return _integration.fallback_merge(all_findings, id_prefix="PINT")


class PlotFindingsIntegrator(BaseFindingsIntegrator):
    """Findings integrator for plot review (see BaseFindingsIntegrator)."""

    def _collect_raw_findings(self, output_dir):
        return _collect_raw_findings(output_dir)

    def _prepare(self, output_dir, *, plot_filepath, **kwargs):
        if not os.path.exists(plot_filepath):
            logger.error(f"Plot file '{plot_filepath}' does not exist.")
            return None
        basename = os.path.basename(plot_filepath)
        plot_stem = os.path.splitext(basename)[0]
        return IntegrationContext(
            target_text=read_file(plot_filepath),
            yaml_path=project_paths.get_plot_findings_yaml_path(output_dir, plot_stem),
            report_path=project_paths.get_plot_report_md_path(output_dir, plot_stem),
        )

    def _run_integration_llm(self, output_dir, target_text, raw_findings_text):
        return run_integration_llm(
            output_dir, target_text, raw_findings_text, self.model
        )

    def _fallback_merge(self, all_findings):
        return _fallback_merge(all_findings)

    def _generate_markdown_report(self, findings, output_md):
        generate_markdown_report(findings, output_md)


def integrate_plot_findings_in_dir(output_dir, plot_filepath, model):
    """Integrates and resolves conflicts in parallel plot review findings."""
    return PlotFindingsIntegrator(model).run(output_dir, plot_filepath=plot_filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Integrate and resolve conflicts in parallel plot review findings."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Directory containing the review output YAML files.",
    )
    parser.add_argument(
        "--plot-file",
        required=True,
        help="Path to the original plot file.",
    )
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="AI Model to use for the merging process.",
    )
    args = parser.parse_args()

    success = integrate_plot_findings_in_dir(args.dir, args.plot_file, args.model)
    if not success:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
