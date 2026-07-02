import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
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


class CommandRunner:
    """Interface / Implementation for executing external commands."""

    def run(
        self, cmd: list[str], capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd, check=True, capture_output=capture_output, text=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Command '{' '.join(cmd)}' failed with exit code {e.returncode}. Stderr: {e.stderr}"
            )
            raise PipelineError(f"External command failed: {e.stderr}") from e
        except Exception as e:
            logger.error(f"Unexpected error executing command '{' '.join(cmd)}': {e}")
            raise PipelineError(f"Command execution error: {e}") from e


class BaseReviewPipeline(ABC):
    """Abstract base class representing a review pipeline."""

    def __init__(
        self,
        target_file: str,
        model: str = "Gemini 3.5 Flash (High)",
        output_dir_override: str | None = None,
        workers: int = 2,
        runner: CommandRunner | None = None,
    ):
        self.target_path = Path(target_file)
        self.model = model
        self.workers = workers
        self.runner = runner or CommandRunner()
        self.basename, self.output_dir = self._resolve_output_dir(output_dir_override)

    @abstractmethod
    def _resolve_output_dir(self, args_dir: str | None) -> tuple[str, str]:
        pass

    @abstractmethod
    def execute(self) -> None:
        pass

    def run_single_review_skill(
        self, skill_name: str, target_text: str, output_file: str
    ) -> tuple[str, bool, str]:
        """Executes a single review skill via ReviewSkillTask."""
        logger.info(f"[{skill_name}] Preparing review prompt...")
        task = ReviewSkillTask(model=self.model)
        input_data = ReviewSkillInput(
            skill_name=skill_name, target_text=target_text, output_dir=self.output_dir
        )

        logger.info(f"[{skill_name}] Running AgyClient ({self.model})...")
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
            raise ReviewSkillExecutionError(
                f"Unexpected error in {skill_name}: {e}"
            ) from e

    def run_parallel_review_skills(
        self, target_text: str, review_skills: dict[str, str]
    ) -> None:
        """Executes review skills in parallel using ThreadPoolExecutor."""
        results = []
        logger.info(f"Spawning {len(review_skills)} review skills in parallel...")
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {}
            for skill, yaml_name in review_skills.items():
                output_yaml = os.path.join(self.output_dir, yaml_name)
                futures[
                    executor.submit(
                        self.run_single_review_skill,
                        skill,
                        target_text,
                        output_yaml,
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
                    logger.error(
                        f"[FAIL] {skill} generated an unexpected exception: {exc}"
                    )
                    results.append((skill, False, str(exc)))


class TextReviewPipeline(BaseReviewPipeline):
    """Pipeline for reviewing novel drafts (text)."""

    def _resolve_output_dir(self, args_dir: str | None) -> tuple[str, str]:
        if project_paths.DEFAULT_RESULTS_DIR in self.target_path.parts:
            idx = self.target_path.parts.index(project_paths.DEFAULT_RESULTS_DIR)
            if idx + 1 < len(self.target_path.parts):
                basename = self.target_path.parts[idx + 1]
                output_dir = project_paths.get_output_dir(basename)
                return basename, output_dir

        basename = self.target_path.stem
        output_dir = args_dir if args_dir else project_paths.get_output_dir(basename)
        return basename, output_dir

    def run_formatter(self, input_file: str, output_file: str) -> None:
        """Runs the novel mechanical formatter on the input file."""
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

        cmd = [
            "poetry",
            "run",
            "python",
            formatter_script,
            input_file,
            "-o",
            output_file,
        ]
        logger.info(f"Running mechanical formatter: {' '.join(cmd)}")
        try:
            self.runner.run(cmd)
        except PipelineError as e:
            raise FormattingError(f"Mechanical formatter failed: {e}") from e

    def run_filter_context(self, formatted_file: str, output_file: str) -> None:
        """Runs the filter_context script to extract relevant settings."""
        filter_script = project_paths.get_src_path("filter_context.py")
        if not os.path.exists(filter_script):
            logger.warning("filter_context.py not found. Skipping context filtering.")
            return

        cmd = ["poetry", "run", "python", filter_script, formatted_file, output_file]
        logger.info(f"Running context filter: {' '.join(cmd)}")
        try:
            self.runner.run(cmd)
        except PipelineError as e:
            raise ContextFilteringError(f"Context filter failed: {e}") from e

    def archive_previous_review(self, target_path: Path | None = None) -> None:
        """Archives the current review results into history/v{version}/."""
        findings_file = project_paths.get_findings_yaml_path(
            self.output_dir, self.basename
        )
        if not os.path.exists(findings_file):
            return

        from src.services import novel_service

        novel_service.archive_current_state(
            self.basename,
            extra_novel_path=str(target_path) if target_path else None,
            output_dir=self.output_dir,
        )

        # Clean up
        for src_path in [
            project_paths.get_findings_yaml_path(self.output_dir, self.basename),
            project_paths.get_report_md_path(self.output_dir, self.basename),
        ]:
            if os.path.exists(src_path):
                os.remove(src_path)

    def _integrate_findings(self) -> None:
        """Helper to invoke finding integration module."""
        from src import integrate_findings

        logger.info(
            f"Calling: integrate_findings.integrate_findings_in_dir(output_dir='{self.output_dir}', model='{self.model}')"
        )
        try:
            success = integrate_findings.integrate_findings_in_dir(
                self.output_dir, self.model
            )
            if not success:
                raise IntegrationError("Failed to integrate findings in directory.")
        except IntegrationError:
            raise
        except Exception as e:
            raise IntegrationError(f"Unexpected integration error: {e}") from e

    def execute(self, no_server: bool = False) -> None:
        """Runs the entire novel review pipeline."""
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("=== Review Pipeline Starting ===")
        logger.info(f"Target: {self.target_path}")
        logger.info(f"Output Directory: {self.output_dir}")
        logger.info(f"Model: {self.model}")

        formatted_draft = project_paths.get_formatted_draft_path(
            self.output_dir, self.basename
        )
        findings_file = project_paths.get_findings_yaml_path(
            self.output_dir, self.basename
        )

        # Step 1: Format
        if os.path.exists(findings_file):
            self.archive_previous_review(target_path=self.target_path)
            logger.info(f"Re-reviewing existing formatted draft: {formatted_draft}")
        elif not os.path.exists(formatted_draft):
            self.run_formatter(str(self.target_path), formatted_draft)
            logger.info(f"Format completed: {formatted_draft}")
        else:
            logger.info(
                f"Formatted draft already exists. Skipping formatting: {formatted_draft}"
            )

        # Step 2: Run Context Filter
        filtered_context = project_paths.get_filtered_context_path(self.output_dir)
        self.run_filter_context(formatted_draft, filtered_context)

        # Read formatted draft text
        target_text = read_file(formatted_draft)

        # Step 3: Run parallel reviews
        self.run_parallel_review_skills(target_text, project_paths.TEXT_REVIEW_SKILLS)

        # Step 4: Run integration report
        self._integrate_findings()
        logger.info("Reports integrated successfully.")
        logger.info(
            f"Consolidated Report: {project_paths.get_report_md_path(self.output_dir, self.basename)}"
        )
        logger.info(
            f"Consolidated YAML  : {project_paths.get_findings_yaml_path(self.output_dir, self.basename)}"
        )

        # Step 5: Start Review Editor Server
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
                    project_paths.get_findings_yaml_path(
                        self.output_dir, self.basename
                    ),
                ]
                logger.info(f"Running: {' '.join(cmd)}")
                self.runner.run(cmd, capture_output=False)
            else:
                logger.warning("review_server.py not found. Interactive UI skipped.")

        logger.info("=== Review Pipeline Finished ===")


class PlotReviewPipeline(BaseReviewPipeline):
    """Pipeline for reviewing novel plots."""

    def _resolve_output_dir(self, args_dir: str | None) -> tuple[str, str]:
        basename = self.target_path.stem
        output_dir = args_dir if args_dir else project_paths.get_output_dir(basename)
        return basename, output_dir

    def archive_previous_review(self) -> None:
        """Archives the current plot review results into a history directory."""
        findings_file = project_paths.get_plot_findings_yaml_path(
            self.output_dir, self.basename
        )
        if not os.path.exists(findings_file):
            return

        history_dir = project_paths.get_history_dir(self.output_dir)
        os.makedirs(history_dir, exist_ok=True)

        existing_versions = []
        version_pattern = re.compile(rf"v(\d+)_(?:{re.escape(self.basename)})_")
        if os.path.exists(history_dir):
            for f in os.listdir(history_dir):
                match = version_pattern.match(f)
                if match:
                    existing_versions.append(int(match.group(1)))

        next_version = max(existing_versions) + 1 if existing_versions else 1
        v_prefix = f"v{next_version}"

        logger.info(
            f"Existing plot review findings found. Archiving to history/{v_prefix}_{self.basename}_..."
        )

        files_to_archive = {
            project_paths.PLOT_FINDINGS_YAML_TEMPLATE.format(
                basename=self.basename
            ): f"{v_prefix}_{self.basename}_plot_findings.yaml",
            project_paths.PLOT_REPORT_MD_TEMPLATE.format(
                basename=self.basename
            ): f"{v_prefix}_{self.basename}_plot_report.md",
        }

        for src_name, dest_name in files_to_archive.items():
            src_path = os.path.join(self.output_dir, src_name)
            dest_path = os.path.join(history_dir, dest_name)
            if os.path.exists(src_path):
                shutil.copy2(src_path, dest_path)
                logger.info(f"Archived: {src_name} -> history/{dest_name}")

        # Clean up
        for src_path in [
            project_paths.get_plot_findings_yaml_path(self.output_dir, self.basename),
            project_paths.get_plot_report_md_path(self.output_dir, self.basename),
        ]:
            if os.path.exists(src_path):
                os.remove(src_path)

    def _integrate_findings(self) -> None:
        """Helper to invoke plot finding integration module."""
        from src import integrate_plot_findings

        logger.info("Integrating plot review results...")
        try:
            success = integrate_plot_findings.integrate_plot_findings_in_dir(
                self.output_dir, str(self.target_path), self.model
            )
            if not success:
                raise IntegrationError(
                    "Failed to integrate plot findings in directory."
                )
        except IntegrationError:
            raise
        except Exception as e:
            raise IntegrationError(f"Unexpected plot integration error: {e}") from e

    def execute(self) -> None:
        """Runs the parallel plot review pipeline."""
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("=== Plot Review Pipeline Starting ===")
        logger.info(f"Target Plot: {self.target_path}")
        logger.info(f"Output Directory: {self.output_dir}")
        logger.info(f"Model: {self.model}")

        self.archive_previous_review()

        target_text = read_file(str(self.target_path))
        if not target_text:
            raise PipelineError(f"Could not read target plot file: {self.target_path}")

        # Step 2: Run parallel reviews
        self.run_parallel_review_skills(target_text, project_paths.PLOT_REVIEW_SKILLS)

        # Step 3: Run integration report
        self._integrate_findings()
        logger.info("Plot reports integrated successfully.")
        logger.info(
            f"Consolidated Report: {project_paths.get_plot_report_md_path(self.output_dir, self.basename)}"
        )
        logger.info(
            f"Consolidated YAML  : {project_paths.get_plot_findings_yaml_path(self.output_dir, self.basename)}"
        )

        logger.info("=== Plot Review Pipeline Finished ===")
