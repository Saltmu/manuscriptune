import subprocess
import threading
import time
from collections.abc import Callable


class AgyClientError(Exception):
    """Base exception for AgyClient errors."""

    pass


class AgyNotFoundError(AgyClientError):
    """Raised when the 'agy' CLI command is not found."""

    pass


class AgyClient:
    """A wrapper for interacting with the Antigravity CLI (agy).

    Provides unified error handling, exponential backoff retries, and streaming support.
    """

    def __init__(
        self,
        model: str = "Gemini 3.5 Flash (High)",
        max_retries: int = 3,
        initial_delay: float = 1.0,
    ):
        self.model = model
        self.max_retries = max_retries
        self.initial_delay = initial_delay

    def generate(
        self, prompt: str, callback: Callable[[str], None] | None = None
    ) -> str:
        """Sends the prompt to agy and returns the generated response.

        If a callback is provided, the output is streamed line by line to the callback.
        """
        cmd = ["agy", "-p", "", "--model", self.model]

        last_exception = None
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            try:
                if callback is not None:
                    return self._generate_stream(cmd, prompt, callback)
                else:
                    return self._generate_normal(cmd, prompt)
            except AgyNotFoundError as e:
                # If CLI is not found, retrying will not help.
                raise e
            except AgyClientError as e:
                last_exception = e
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e

        if last_exception:
            raise last_exception
        raise AgyClientError("Failed to generate content.")

    def _generate_normal(self, cmd: list[str], prompt: str) -> str:
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            stdout, stderr = process.communicate(input=prompt)
        except FileNotFoundError as e:
            raise AgyNotFoundError("Antigravity CLI (agy) not found.") from e
        except Exception as e:
            raise AgyClientError(f"Unexpected error when calling agy: {str(e)}") from e

        if process.returncode != 0:
            raise AgyClientError(
                f"agy error (exit code {process.returncode}): {stderr}"
            )

        return stdout

    def _generate_stream(
        self, cmd: list[str], prompt: str, callback: Callable[[str], None]
    ) -> str:
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
                # write_stdin is only spawned after the check, so process.stdin is guaranteed not to be None
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
            raise AgyClientError(
                f"agy error (exit code {process.returncode}): {stderr}"
            )

        return "".join(output_chunks)
