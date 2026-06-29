import subprocess
import threading
from collections.abc import Callable
from typing import Any

from src.utils.ai_exceptions import AgyClientError, AgyNotFoundError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AgyCLIExecutor:
    """Handles low-level subprocess execution of the Antigravity CLI (agy)."""

    def execute(self, cmd: list[str], prompt: str | None = None) -> str:
        """Executes a command and returns the standard output.

        Raises AgyNotFoundError if the executable is not found.
        Raises AgyClientError on execution failures.
        """
        try:
            kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
            }
            if prompt is not None:
                kwargs["stdin"] = subprocess.PIPE
            process = subprocess.Popen(cmd, **kwargs)
            stdout, stderr = process.communicate(input=prompt)
            assert isinstance(stdout, str)
            assert isinstance(stderr, str)
        except FileNotFoundError as e:
            logger.error(
                "Antigravity CLI (agy) executable not found in PATH.",
                exc_info=True,
            )
            raise AgyNotFoundError("Antigravity CLI (agy) not found.") from e
        except Exception as e:
            logger.error(f"Unexpected error when calling agy: {e}", exc_info=True)
            raise AgyClientError(f"Unexpected error when calling agy: {str(e)}") from e

        if process.returncode != 0:
            logger.error(
                "agy execution failed with return code"
                f" {process.returncode}: {stderr}"
            )
            raise AgyClientError(
                f"agy error (exit code {process.returncode}): {stderr}"
            )

        return stdout

    def execute_stream(
        self, cmd: list[str], prompt: str, callback: Callable[[str], None]
    ) -> str:
        """Executes a command streaming its output line by line.

        Raises AgyNotFoundError if the executable is not found.
        Raises AgyClientError on execution failures.
        """
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError as e:
            raise AgyNotFoundError("Antigravity CLI (agy) not found.") from e
        except Exception as e:
            raise AgyClientError(f"Unexpected error when calling agy: {str(e)}") from e

        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise AgyClientError("Failed to initialize subprocess pipes.")

        def write_stdin():
            try:
                # process.stdin is guaranteed not to be None here
                process.stdin.write(prompt)
                process.stdin.close()
            except Exception:
                pass

        stdin_thread = threading.Thread(target=write_stdin)
        stdin_thread.start()

        output_chunks = []
        try:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    callback(line)
                    output_chunks.append(line)
        finally:
            stdin_thread.join()

        stderr = process.stderr.read()
        if process.returncode != 0:
            logger.error(
                "agy streaming execution failed with return code"
                f" {process.returncode}: {stderr}"
            )
            raise AgyClientError(
                f"agy error (exit code {process.returncode}): {stderr}"
            )

        return "".join(output_chunks)
