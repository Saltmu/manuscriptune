import os

from src.utils import project_paths
from src.utils.ai_exceptions import ContextFilteringError, PipelineError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextFilterPhase:
    """Phase responsible for running the context filtering script."""

    def __init__(self, runner):
        self.runner = runner

    def run(self, formatted_file: str, output_file: str) -> None:
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
