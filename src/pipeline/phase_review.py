import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.ai_client import AgyClientError
from src.utils.ai_exceptions import ReviewSkillExecutionError
from src.utils.ai_task import ReviewSkillInput, ReviewSkillTask
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReviewPhase:
    """Phase responsible for executing multiple review skills in parallel."""

    def __init__(self, model: str, output_dir: str, workers: int = 2):
        self.model = model
        self.output_dir = output_dir
        self.workers = workers

    def run_single_review_skill(
        self, skill_name: str, target_text: str, output_file: str
    ) -> tuple[str, bool, str]:
        """Executes a single review skill via ReviewSkillTask."""
        logger.info(f"[{skill_name}] Preparing review prompt...")
        task = ReviewSkillTask(model=self.model)
        input_data = ReviewSkillInput(
            skill_name=skill_name,
            target_text=target_text,
            output_dir=self.output_dir,
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
