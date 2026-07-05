import pytest

from src.utils.cancellation import CancellationToken, PipelineCancelledError


def test_cancellation_token_not_cancelled_by_default():
    token = CancellationToken()
    assert not token.is_cancelled()
    token.check()  # should not raise


def test_cancellation_token_cancel_and_check():
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled()
    with pytest.raises(PipelineCancelledError):
        token.check()
