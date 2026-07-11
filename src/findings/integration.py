"""Shared logic for merging parallel review findings into a single result.

Used by both ``src/cli/integrate_findings.py`` (novel text review) and
``src/cli/integrate_plot_findings.py`` (plot review), which differ only in
YAML discovery strategy, path resolution, and report wording.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.utils.ai_client import AgyClientError
from src.utils.logger import get_logger
from src.utils.yaml_handler import YamlHandler

logger = get_logger(__name__)

_SEVERITY_EMOJI = {"high": "🚨", "medium": "⚠️", "low": "💡", "info": "ℹ️"}
_SEVERITY_ORDER = ["high", "medium", "low", "info"]


def parse_yaml_file(filepath: str) -> list[dict]:
    return YamlHandler.load_findings(filepath)


def generate_markdown_report(
    findings: list[dict],
    output_md: str,
    *,
    report_title: str,
    no_findings_message: str,
    summary_message: str,
    severity_titles: dict[str, str],
    item_label: str,
    suggestion_label: str,
    default_id_prefix: str,
) -> None:
    """Generates a human-readable markdown summary report from integrated findings."""
    md = f"{report_title}\n\n"
    if not findings:
        md += f"{no_findings_message}\n"
    else:
        md += f"{summary_message.format(count=len(findings))}\n\n"

        severities: dict[str, list[dict]] = {
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
        }
        for f in findings:
            sev = f.get("severity", "low").lower()
            if sev in severities:
                severities[sev].append(f)
            else:
                severities["low"].append(f)

        for sev_level in _SEVERITY_ORDER:
            level_findings = severities[sev_level]
            if not level_findings:
                continue

            emoji = _SEVERITY_EMOJI[sev_level]
            title = severity_titles[sev_level]

            md += f"## {emoji} {title} ({len(level_findings)}件)\n\n"

            for item in level_findings:
                md += f"### [{item.get('id', default_id_prefix)}] {item.get('category', '指摘')} (場所: {item.get('location', '不明')})\n"
                md += f"- **{item_label}:** `{item.get('original', '')}`\n"
                md += f"- **分析:** {item.get('analysis', '')}\n"
                md += f"- **{suggestion_label}:** {item.get('suggestion', '')}\n\n"

    with open(output_md, "w", encoding="utf-8") as out_f:
        out_f.write(md)


def run_integration_llm(
    target_text: str,
    raw_findings_text: str,
    model: str,
    *,
    task_cls: Any,
    input_cls: Any,
    log_prefix: str,
) -> Any:
    """Calls the given integration task class to merge and resolve conflicts."""
    logger.info(f"Sending {log_prefix} request to AgyClient ({model})...")
    task = task_cls(model=model)
    input_data = input_cls(target_text=target_text, raw_findings_text=raw_findings_text)
    try:
        return task.execute(input_data)
    except AgyClientError as e:
        logger.error(f"Error calling AgyClient: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling AgyClient: {e}")
        return None


def fallback_merge(
    all_findings: list[dict], *, id_prefix: str, extra_metadata: dict | None = None
) -> str:
    """Performs mechanical fallback merging when LLM integration is unavailable."""
    merged_findings = []
    for idx, f in enumerate(all_findings, 1):
        f_copy = f.copy()
        f_copy["id"] = f"{id_prefix}-{idx:03d}"
        if "_source_file" in f_copy:
            del f_copy["_source_file"]
        merged_findings.append(f_copy)

    result: dict = {"findings": merged_findings}
    if extra_metadata:
        result["_metadata"] = extra_metadata
    return YamlHandler.dump(result)


@dataclass
class IntegrationContext:
    """Resolved inputs/outputs for a single integration run."""

    target_text: str
    yaml_path: str
    report_path: str


class BaseFindingsIntegrator(ABC):
    """Common flow for merging parallel review findings into a single result.

    Subclasses supply the findings-type-specific pieces (discovery strategy,
    path resolution, and the underlying LLM/report configuration) by
    implementing the abstract hooks below; ``run()`` implements the shared
    "check inputs -> collect -> merge (LLM or fallback) -> write outputs"
    sequence that used to be duplicated between the text and plot CLIs.
    """

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def _collect_raw_findings(self, output_dir: str) -> list[dict]: ...

    @abstractmethod
    def _prepare(self, output_dir: str, **kwargs: Any) -> IntegrationContext | None:
        """Validates inputs and resolves target text / output paths.

        Returns ``None`` (after logging the reason) if inputs are invalid.
        """
        ...

    @abstractmethod
    def _run_integration_llm(
        self, output_dir: str, target_text: str, raw_findings_text: str
    ) -> str | None: ...

    @abstractmethod
    def _fallback_merge(self, all_findings: list[dict]) -> str: ...

    @abstractmethod
    def _generate_markdown_report(
        self, findings: list[dict], output_md: str
    ) -> None: ...

    def run(self, output_dir: str, **kwargs: Any) -> bool:
        if not os.path.exists(output_dir):
            logger.error(f"Directory '{output_dir}' does not exist.")
            return False

        ctx = self._prepare(output_dir, **kwargs)
        if ctx is None:
            return False

        all_findings = self._collect_raw_findings(output_dir)

        if not all_findings:
            logger.info("No findings to merge. Writing empty integrated findings.")
            with open(ctx.yaml_path, "w", encoding="utf-8") as f:
                f.write("findings: []\n")
            self._generate_markdown_report([], ctx.report_path)
            logger.info("Done.")
            return True

        raw_findings_text = YamlHandler.dump({"findings": all_findings})

        merged_yaml_content = self._run_integration_llm(
            output_dir, ctx.target_text, raw_findings_text
        )

        if not merged_yaml_content:
            logger.error(
                "LLM integration failed. Performing mechanical fallback merging."
            )
            merged_yaml_content = self._fallback_merge(all_findings)

        with open(ctx.yaml_path, "w", encoding="utf-8") as f:
            f.write(merged_yaml_content + "\n")
        logger.info(f"Saved integrated findings to {ctx.yaml_path}")

        try:
            merged_findings_list = YamlHandler.load_findings(merged_yaml_content)
        except Exception:
            merged_findings_list = []
            logger.warning(
                "Could not parse merged YAML back for Markdown report generation."
            )

        self._generate_markdown_report(merged_findings_list, ctx.report_path)
        logger.info(f"Saved Markdown report to {ctx.report_path}")
        return True
