import time
from collections.abc import Callable
from typing import TypeVar

from src.utils.ai_exceptions import AgyClientError, AgyNotFoundError
from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class RetryExecutor:
    """Handles retry policy with exponential backoff for CLI commands."""

    def __init__(self, max_retries: int = 3, initial_delay: float = 1.0):
        self.max_retries = max_retries
        self.initial_delay = initial_delay

    def execute(self, action: Callable[[], T]) -> T:
        """Executes the action with exponential backoff on AgyClientError.

        AgyNotFoundError is raised immediately without retries.
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            try:
                return action()
            except AgyNotFoundError as e:
                # Do not retry for AgyNotFoundError
                raise e
            except AgyClientError as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries + 1} failed:"
                        f" {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(
                        "Execution failed after"
                        f" {self.max_retries + 1} attempts. Final error: {e}",
                        exc_info=True,
                    )
                    raise e

        if last_exception:
            raise last_exception
        raise AgyClientError("Failed to execute action.")
