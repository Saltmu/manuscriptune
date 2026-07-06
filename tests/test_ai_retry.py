from unittest.mock import MagicMock, patch

import pytest

from src.utils.ai_exceptions import AgyClientError, AgyNotFoundError
from src.utils.ai_retry import RetryExecutor


def test_retry_executor_success():
    mock_action = MagicMock(return_value="Success")

    executor = RetryExecutor(max_retries=3, initial_delay=0.01)
    result = executor.execute(mock_action)

    assert result == "Success"
    mock_action.assert_called_once()


@patch("time.sleep")
def test_retry_executor_retry_and_fail(mock_sleep):
    mock_action = MagicMock(side_effect=AgyClientError("CLI failed"))

    executor = RetryExecutor(max_retries=2, initial_delay=0.1)
    with pytest.raises(AgyClientError) as exc_info:
        executor.execute(mock_action)

    assert "CLI failed" in str(exc_info.value)
    # 1 initial + 2 retries = 3 calls
    assert mock_action.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.1)
    mock_sleep.assert_any_call(0.2)


@patch("time.sleep")
def test_retry_executor_no_retry_for_not_found(mock_sleep):
    mock_action = MagicMock(side_effect=AgyNotFoundError("Not found"))

    executor = RetryExecutor(max_retries=3, initial_delay=0.1)
    with pytest.raises(AgyNotFoundError) as exc_info:
        executor.execute(mock_action)

    assert "Not found" in str(exc_info.value)
    assert mock_action.call_count == 1
    assert mock_sleep.call_count == 0
