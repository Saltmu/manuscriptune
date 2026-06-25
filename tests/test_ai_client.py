import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.utils.ai_client import AgyClient, AgyClientError, AgyNotFoundError


@patch("subprocess.Popen")
def test_agy_client_generate_success(mock_popen):
    # Mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = ("Generated output text", "")
    mock_popen.return_value = mock_process

    client = AgyClient(model="Gemini 3.5 Flash (High)")
    result = client.generate("Input prompt")

    assert result == "Generated output text"
    mock_popen.assert_called_once_with(
        ["agy", "-p", "", "--model", "Gemini 3.5 Flash (High)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    mock_process.communicate.assert_called_once_with(input="Input prompt")


@patch("subprocess.Popen")
@patch("time.sleep")  # to avoid delay during tests
def test_agy_client_retry_on_failure(mock_sleep, mock_popen):
    # Mock subprocess failure (non-zero exit code)
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = ("", "Some CLI Error")
    mock_popen.return_value = mock_process

    client = AgyClient(
        model="Gemini 3.5 Flash (High)", max_retries=3, initial_delay=0.1
    )

    with pytest.raises(AgyClientError) as exc_info:
        client.generate("Input prompt")

    assert "agy error" in str(exc_info.value)
    # 3 retries + 1 initial attempt = 4 calls total
    assert mock_popen.call_count == 4
    assert mock_sleep.call_count == 3


@patch("subprocess.Popen")
def test_agy_client_not_found(mock_popen):
    # Mock FileNotFoundError when running agy CLI
    mock_popen.side_effect = FileNotFoundError()

    client = AgyClient()
    with pytest.raises(AgyNotFoundError) as exc_info:
        client.generate("Input prompt")

    assert "not found" in str(exc_info.value)


@patch("subprocess.Popen")
def test_agy_client_stream(mock_popen):
    # Mock subprocess streaming output
    mock_process = MagicMock()
    mock_process.poll.return_value = 0
    mock_process.stdout.readline.side_effect = [
        "Line 1\n",
        "Line 2\n",
        "",
    ]
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    client = AgyClient()
    collected = []

    def callback(text):
        collected.append(text)

    # Use stream parameter
    result = client.generate("Input prompt", callback=callback)

    assert result == "Line 1\nLine 2\n"
    assert collected == ["Line 1\n", "Line 2\n"]
    mock_process.stdin.write.assert_called_once_with("Input prompt")
    mock_process.stdin.close.assert_called_once()
