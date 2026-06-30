import argparse
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.utils import project_paths
from src.utils.ai_client import AgyClientError
from src.utils.ai_exceptions import (
    ContextFilteringError,
    FormattingError,
    IntegrationError,
    PipelineError,
    ReviewSkillExecutionError,
)
from src.utils.ai_task import ReviewSkillInput, ReviewSkillTask
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)


def archive_previous_review(output_dir, basename, target_path=None):
    """
    Archives the current [basename]_formatted.txt, [basename]_findings.yaml,
    [basename]_report.md, and the original target file into a history/v{version}/ directory.
    """
    history_dir = project_paths.get_history_dir(output_dir)
    findings_file = project_paths.get_findings_yaml_path(output_dir, basename)

    if not os.path.exists(findings_file):
        return

    os.makedirs(history_dir, exist_ok=True)

    # Determine version number (v1, v2, v3...)
    existing_versions = []
    version_pattern = re.compile(r"^v(\d+)$")
    if os.path.exists(history_dir):
        for d in os.listdir(history_dir):
            if os.path.isdir(os.path.join(history_dir, d)):
                match = version_pattern.match(d)
                if match:
                    existing_versions.append(int(match.group(1)))

    next_version = max(existing_versions) + 1 if existing_versions else 1
    v_prefix = f"v{next_version}"
    version_dir = project_paths.get_version_dir(output_dir, v_prefix)
    os.makedirs(version_dir, exist_ok=True)

    logger.info(f"Existing review findings found. Archiving to history/{v_prefix}/...")

    # Files to archive
    files_to_archive = {
        project_paths.FORMATTED_DRAFT_TEMPLATE.format(
            basename=basename
        ): project_paths.FORMATTED_DRAFT_TEMPLATE.format(basename=basename),
        project_paths.FINDINGS_YAML_TEMPLATE.format(
            basename=basename
        ): project_paths.FINDINGS_YAML_TEMPLATE.format(basename=basename),
        project_paths.REPORT_MD_TEMPLATE.format(
            basename=basename
        ): project_paths.REPORT_MD_TEMPLATE.format(basename=basename),
        project_paths.FILTERED_CONTEXT_NAME: project_paths.FILTERED_CONTEXT_NAME,
    }

    for src_name, dest_name in files_to_archive.items():
        src_path = os.path.join(output_dir, src_name)
        dest_path = os.path.join(version_dir, dest_name)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dest_path)
            logger.info(f"Archived: {src_name} -> history/{v_prefix}/{dest_name}")

    # Archive original novel text (target_path)
    if target_path:
        target_path_obj = Path(target_path)
        if target_path_obj.exists():
            dest_original = os.path.join(version_dir, target_path_obj.name)
            shutil.copy2(str(target_path_obj), dest_original)
            logger.info(
                f"Archived Original Text: {target_path_obj.name} -> history/{v_prefix}/{target_path_obj.name}"
            )

    # Clean up current findings and report so they are regenerated
    for src_path in [
        project_paths.get_findings_yaml_path(output_dir, basename),
        project_paths.get_report_md_path(output_dir, basename),
    ]:
        if os.path.exists(src_path):
            os.remove(src_path)


def run_formatter(input_file, output_file):
    """
    Runs the novel mechanical formatter on the input file.
    """
    formatter_script = os.path.join(
        project_paths.get_skills_dir(),
        "novel-formatter",
        "scripts",
        "novel_formatter_helper.py",
    )
    if not os.path.exists(formatter_script):
        logger.warning(
            f"Formatter script '{formatter_script}' not found. Performing fallback copy."
        )
        content = read_file(input_file)
        content = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", content)
        content = re.sub(r"\(\d+(?:,\s*\d+)*\)", "", content)
        content = re.sub(r"【\d+(?:,\s*\d+)*】", "", content)
        content = re.sub(r"([。、！？])[\t 　]+", r"\1", content)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        return

    cmd = ["poetry", "run", "python", formatter_script, input_file, "-o", output_file]
    logger.info(f"Running mechanical formatter: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Formatter process failed with exit code {e.returncode}. Stderr: {e.stderr}"
        )
        raise FormattingError(f"Mechanical formatter failed: {e.stderr}") from e
    except Exception as e:
        logger.error(f"Unexpected error running formatter: {e}")
        raise FormattingError(f"Unexpected formatting error: {e}") from e


def run_filter_context(formatted_file, output_file):
    """
    Runs the filter_context script to extract relevant settings.
    """
    filter_script = project_paths.get_src_path("filter_context.py")
    if not os.path.exists(filter_script):
        logger.warning("filter_context.py not found. Skipping context filtering.")
        return False

    cmd = ["poetry", "run", "python", filter_script, formatted_file, output_file]
    logger.info(f"Running context filter: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ContextFilteringError(
                f"Context filter failed with exit code {res.returncode}. Stderr: {res.stderr}"
            )
        return True
    except subprocess.SubprocessError as e:
        raise ContextFilteringError(
            f"Failed to execute context filter subprocess: {e}"
        ) from e


def run_single_review_skill(skill_name, target_text, output_file, model, output_dir):
    """
    Executes a single review skill via ReviewSkillTask.
    """
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
            f"Review skill {skill_name} failed via AgyClient: {e}"
        ) from e
    except Exception as e:
        logger.error(f"[{skill_name}] Unexpected exception: {e}")
        raise ReviewSkillExecutionError(f"Unexpected error in {skill_name}: {e}") from e


def _resolve_output_dir(target_path: Path, args_dir: str | None) -> tuple[str, str]:
    """
    Resolves basename and output directory.
    """
    if project_paths.DEFAULT_RESULTS_DIR in target_path.parts:
        idx = target_path.parts.index(project_paths.DEFAULT_RESULTS_DIR)
        if idx + 1 < len(target_path.parts):
            basename = target_path.parts[idx + 1]
            output_dir = project_paths.get_output_dir(basename)
            return basename, output_dir

    basename = target_path.stem
    output_dir = args_dir if args_dir else project_paths.get_output_dir(basename)
    return basename, output_dir


def _run_step_format(
    target_path: Path, formatted_draft: str, output_dir: str, basename: str
) -> None:
    """
    Executes Step 1: mechanical formatter and archiving if needed.
    """
    findings_file = project_paths.get_findings_yaml_path(output_dir, basename)
    is_rereview = os.path.exists(findings_file)

    if is_rereview:
        archive_previous_review(output_dir, basename, target_path=target_path)
        logger.info(f"Re-reviewing existing formatted draft: {formatted_draft}")
    elif not os.path.exists(formatted_draft):
        try:
            run_formatter(str(target_path), formatted_draft)
            logger.info(f"Format completed: {formatted_draft}")
        except FormattingError as e:
            logger.error(f"Formatting failed: {e}")
            raise
    else:
        logger.info(
            f"Formatted draft already exists. Skipping formatting: {formatted_draft}"
        )


def _run_step_parallel_reviews(
    target_text: str, output_dir: str, model: str, workers: int
) -> None:
    """
    Executes Step 3: parallel execution of review skills.
    """
    review_skills = project_paths.TEXT_REVIEW_SKILLS
    results = []

    logger.info(f"Spawning {len(review_skills)} review skills in parallel...")
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


def _run_step_integration(output_dir: str, basename: str, model: str) -> None:
    """
    Executes Step 4: integrates all findings into a final report.
    """
    logger.info("Integrating review results...")
    try:
        import integrate_findings

        logger.info(
            f"Calling: integrate_findings.integrate_findings_in_dir(output_dir='{output_dir}', model='{model}')"
        )
        success = integrate_findings.integrate_findings_in_dir(output_dir, model)
        if not success:
            raise IntegrationError("Failed to integrate findings in directory.")
        logger.info("Reports integrated successfully.")
        logger.info(
            f"Consolidated Report: {project_paths.get_report_md_path(output_dir, basename)}"
        )
        logger.info(
            f"Consolidated YAML  : {project_paths.get_findings_yaml_path(output_dir, basename)}"
        )
    except IntegrationError as e:
        logger.error(f"Integration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while calling integrate_findings: {e}")
        raise IntegrationError(f"Unexpected integration error: {e}") from e


def _run_step_server(
    formatted_draft: str, output_dir: str, basename: str, no_server: bool
) -> None:
    """
    Executes Step 5: launches the interactive review editor server.
    """
    if not no_server:
        logger.info("Starting Interactive Review Editor UI...")
        server_script = project_paths.get_src_path("review_server.py")
        if os.path.exists(server_script):
            cmd = [
                "poetry",
                "run",
                "python",
                server_script,
                formatted_draft,
                project_paths.get_findings_yaml_path(output_dir, basename),
            ]
            logger.info(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd)
        else:
            logger.warning("review_server.py not found. Interactive UI skipped.")


def main():
    parser = argparse.ArgumentParser(
        description="Run the entire parallel review pipeline for a novel draft."
    )
    parser.add_argument("target_file", help="Path to the novel txt file to review.")
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
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Skip launching the web server editor at the end.",
    )
    args = parser.parse_args()

    target_path = Path(args.target_file)

    # Smart path resolution
    basename, output_dir = _resolve_output_dir(target_path, args.dir)

    os.makedirs(output_dir, exist_ok=True)

    logger.info("=== Review Pipeline Starting ===")
    logger.info(f"Target: {target_path}")
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"Model: {args.model}")

    try:
        # Step 1: Run Formatter (or Skip if it's a re-review)
        formatted_draft = project_paths.get_formatted_draft_path(output_dir, basename)
        _run_step_format(target_path, formatted_draft, output_dir, basename)

        # Step 2: Run Context Filter
        filtered_context = project_paths.get_filtered_context_path(output_dir)
        run_filter_context(formatted_draft, filtered_context)

        # Read formatted draft text
        target_text = read_file(formatted_draft)

        # Step 3: Run parallel reviews
        _run_step_parallel_reviews(target_text, output_dir, args.model, args.workers)

        # Step 4: Run integration report
        _run_step_integration(output_dir, basename, args.model)

        # Step 5: Start Review Editor Server
        _run_step_server(formatted_draft, output_dir, basename, args.no_server)

    except PipelineError as e:
        logger.error(f"Pipeline execution failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled critical error in pipeline: {e}")
        sys.exit(1)

    logger.info("=== Review Pipeline Finished ===")


if __name__ == "__main__":
    main()
