from collections.abc import Callable

from src.utils.ai_cli_executor import AgyCLIExecutor
from src.utils.ai_exceptions import AgyClientError, AgyNotFoundError
from src.utils.ai_model_parser import AgyModelParser
from src.utils.ai_retry import RetryExecutor
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Re-export exceptions and AgyClient
__all__ = ["AgyClient", "AgyClientError", "AgyNotFoundError"]


class AgyClient:
    """A wrapper for interacting with the Antigravity CLI (agy).

    Provides unified error handling, exponential backoff retries, and streaming support.
    """

    def __init__(
        self,
        model: str = "Gemini 3.5 Flash (High)",
        max_retries: int = 3,
        initial_delay: float = 1.0,
        executor: AgyCLIExecutor | None = None,
    ):
        self.model = model
        self.retry_executor = RetryExecutor(
            max_retries=max_retries, initial_delay=initial_delay
        )
        self.executor = executor or AgyCLIExecutor()

    def generate(
        self, prompt: str, callback: Callable[[str], None] | None = None
    ) -> str:
        """Sends the prompt to agy and returns the generated response.

        If a callback is provided, the output is streamed line by line to the callback.
        """
        logger.info(
            f"Generating content using model: {self.model} (Prompt"
            f" length: {len(prompt)})"
        )
        cmd = ["agy", "-p", "", "--model", self.model]

        if callback is not None:
            return self.retry_executor.execute(
                lambda: self.executor.execute_stream(cmd, prompt, callback)
            )
        else:
            return self.retry_executor.execute(
                lambda: self.executor.execute(cmd, prompt)
            )

    @classmethod
    def list_models(cls, executor: AgyCLIExecutor | None = None) -> list[str]:
        """Runs `agy models` to fetch a list of available models."""
        cmd = ["agy", "models"]
        exec_to_use = executor or AgyCLIExecutor()
        try:
            stdout = exec_to_use.execute(cmd)
        except AgyClientError as e:
            raise AgyClientError(f"Failed to list models: {str(e)}") from e
        return AgyModelParser.parse_models_output(stdout)
