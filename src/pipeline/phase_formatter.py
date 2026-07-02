import os
import re

from src.utils import project_paths
from src.utils.ai_exceptions import FormattingError, PipelineError
from src.utils.file_io import read_file
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FormatterPhase:
    """Phase responsible for running the novel mechanical formatter."""

    def __init__(self, runner):
        self.runner = runner

    def run(self, input_file: str, output_file: str) -> None:
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
