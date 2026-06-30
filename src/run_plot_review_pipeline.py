import argparse
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src import integrate_plot_findings
from src.utils import project_paths
from src.utils.ai_client import AgyClientError
from src.utils.ai_exceptions import (
    IntegrationError,
    PipelineError,
    ReviewSkillExecutionError,
)
from src.utils.ai_task import ReviewSkillInput, ReviewSkillTask
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)


def archive_previous_plot_review(output_dir, basename):
    """Archives the current [basename]_plot_findings.yaml and [basename]_plot_report.md

    into a history directory.
    """
    history_dir = project_paths.get_history_dir(output_dir)
    findings_file = project_paths.get_plot_findings_yaml_path(output_dir, basename)

    if not os.path.exists(findings_file):
        return

    os.makedirs(history_dir, exist_ok=True)

    # Determine version number (v1, v2, v3...)
    existing_versions = []
    version_pattern = re.compile(rf"v(\d+)_(?:{re.escape(basename)})_")
    if os.path.exists(history_dir):
        for f in os.listdir(history_dir):
            match = version_pattern.match(f)
            if match:
                existing_versions.append(int(match.group(1)))

    next_version = max(existing_versions) + 1 if existing_versions else 1
    v_prefix = f"v{next_version}"

    logger.info(
        f"Existing plot review findings found. Archiving to history/{v_prefix}_{basename}_..."
    )

    # Files to archive
    files_to_archive = {
        project_paths.PLOT_FINDINGS_YAML_TEMPLATE.format(
            basename=basename
        ): f"{v_prefix}_{basename}_plot_findings.yaml",
        project_paths.PLOT_REPORT_MD_TEMPLATE.format(
            basename=basename
        ): f"{v_prefix}_{basename}_plot_report.md",
    }

    for src_name, dest_name in files_to_archive.items():
        src_path = os.path.join(output_dir, src_name)
        dest_path = os.path.join(history_dir, dest_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            logger.info(f"Archived: {src_name} -> history/{dest_name}")

    # Clean up current findings and report so they are regenerated
    for src_path in [
        project_paths.get_plot_findings_yaml_path(output_dir, basename),
        project_paths.get_plot_report_md_path(output_dir, basename),
    ]:
        if os.path.exists(src_path):
            os.remove(src_path)


def run_single_review_skill(skill_name, target_text, output_file, model, output_dir):
    """Executes a single review skill via ReviewSkillTask."""
    logger.info(f"[{skill_name}] Preparing review prompt...")
    task = ReviewSkillTask(model=model)
    input_data = ReviewSkillInput(
        skill_name=skill_name, target_text=target_text, output_dir=output_dir
    )

    logger.info(f"[{skill_name}] Running AgyClient ({model})...")
    try:
        yaml_content = task.execute(input_data)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(yaml_content + "\n")

        return skill_name, True, f"Saved to {output_file}"

    except AgyClientError as e:
        logger.error(f"[{skill_name}] AgyClientError: {e}")
        raise ReviewSkillExecutionError(
            f"Plot review skill {skill_name} failed via AgyClient: {e}"
        ) from e
    except Exception as e:
        logger.error(f"[{skill_name}] Unexpected exception: {e}")
        raise ReviewSkillExecutionError(f"Unexpected error in {skill_name}: {e}") from e


def _run_step_parallel_reviews(
    target_text: str, output_dir: str, model: str, workers: int
) -> None:
    """Executes Step 2: parallel execution of review skills."""
    review_skills = project_paths.PLOT_REVIEW_SKILLS
    results = []

    logger.info(f"Spawning {len(review_skills)} plot review skills in parallel...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for skill, yaml_name in review_skills.items():
            output_yaml = os.path.join(output_dir, yaml_name)
            futures[
                executor.submit(
                    run_single_review_skill,
                    skill,
                    target_text,
                    output_yaml,
                    model,
                    output_dir,
                )
            ] = skill

        for future in as_completed(futures):
            skill = futures[future]
            try:
                skill_name, success, msg = future.result()
                results.append((skill_name, success, msg))
                if success:
                    logger.info(f"[OK] {skill_name}: {msg}")
                else:
                    logger.error(f"[FAIL] {skill_name}: {msg}")
            except ReviewSkillExecutionError as exc:
                logger.error(f"[FAIL] {skill} execution failed: {exc}")
                results.append((skill, False, str(exc)))
            except Exception as exc:
                logger.error(f"[FAIL] {skill} generated an unexpected exception: {exc}")
                results.append((skill, False, str(exc)))


def _run_step_integration(
    output_dir: str, target_path: str, model: str, basename: str
) -> None:
    """Executes Step 3: integrates plot findings into a final report."""
    logger.info("Integrating plot review results...")
    try:
        success = integrate_plot_findings.integrate_plot_findings_in_dir(
            output_dir, target_path, model
        )
        if not success:
            raise IntegrationError("Failed to integrate plot findings in directory.")
        logger.info("Plot reports integrated successfully.")
        logger.info(
            f"Consolidated Report: {project_paths.get_plot_report_md_path(output_dir, basename)}"
        )
        logger.info(
            f"Consolidated YAML  : {project_paths.get_plot_findings_yaml_path(output_dir, basename)}"
        )
    except IntegrationError as e:
        logger.error(f"Integration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while calling integrate_plot_findings: {e}")
        raise IntegrationError(f"Unexpected plot integration error: {e}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Run the parallel plot review pipeline."
    )
    parser.add_argument("target_file", help="Path to the plot txt file to review.")
    parser.add_argument(
        "--model",
        default="Gemini 3.5 Flash (High)",
        help="AI Model to use for review skills.",
    )
    parser.add_argument(
        "--dir",
        help=f"Output directory path (defaults to {project_paths.DEFAULT_RESULTS_DIR}/[basename])",
    )
    parser.add_argument(
        "--workers", type=int, default=2, help="Number of parallel worker threads."
    )
    args = parser.parse_args()

    target_path = Path(args.target_file)
    basename = target_path.stem
    output_dir = args.dir if args.dir else project_paths.get_output_dir(basename)

    os.makedirs(output_dir, exist_ok=True)

    logger.info("=== Plot Review Pipeline Starting ===")
    logger.info(f"Target Plot: {target_path}")
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"Model: {args.model}")

    try:
        # Step 1: Archive previous review if exists
        archive_previous_plot_review(output_dir, basename)

        # Read plot text
        target_text = read_file(str(target_path))
        if not target_text:
            raise PipelineError(f"Could not read target plot file: {target_path}")

        # Step 2: Run parallel review skills
        _run_step_parallel_reviews(target_text, output_dir, args.model, args.workers)

        # Step 3: Run integration report
        _run_step_integration(output_dir, str(target_path), args.model, basename)

    except PipelineError as e:
        logger.error(f"Plot review pipeline failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled critical error in plot pipeline: {e}")
        sys.exit(1)

    logger.info("=== Plot Review Pipeline Finished ===")


if __name__ == "__main__":
    main()
