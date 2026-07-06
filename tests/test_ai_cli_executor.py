import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.utils.ai_cli_executor import AgyCLIExecutor
from src.utils.ai_exceptions import AgyClientError, AgyNotFoundError


@patch("subprocess.Popen")
def test_cli_executor_execute_success(mock_popen):
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = ("Success output", "")
    mock_popen.return_value = mock_process

    executor = AgyCLIExecutor()
    result = executor.execute(["agy", "test"], prompt="my prompt")

    assert result == "Success output"
    mock_popen.assert_called_once_with(
        ["agy", "test"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    mock_process.communicate.assert_called_once_with(input="my prompt")


@patch("subprocess.Popen")
def test_cli_executor_execute_not_found(mock_popen):
    mock_popen.side_effect = FileNotFoundError()

    executor = AgyCLIExecutor()
    with pytest.raises(AgyNotFoundError) as exc_info:
        executor.execute(["agy", "test"])

    assert "not found" in str(exc_info.value)


@patch("subprocess.Popen")
def test_cli_executor_execute_failure(mock_popen):
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = ("", "Error occurred")
    mock_popen.return_value = mock_process

    executor = AgyCLIExecutor()
    with pytest.raises(AgyClientError) as exc_info:
        executor.execute(["agy", "test"])

    assert "exit code 1" in str(exc_info.value)


@patch("subprocess.Popen")
def test_cli_executor_execute_stream_success(mock_popen):
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.stdout.readline.side_effect = ["Line 1\n", "Line 2\n", ""]
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    executor = AgyCLIExecutor()
    collected = []

    result = executor.execute_stream(
        ["agy", "stream"], prompt="Stream prompt", callback=collected.append
    )

    assert result == "Line 1\nLine 2\n"
    assert collected == ["Line 1\n", "Line 2\n"]
    mock_process.stdin.write.assert_called_once_with("Stream prompt")
    mock_process.stdin.close.assert_called_once()
