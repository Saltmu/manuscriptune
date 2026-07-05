import asyncio
import time

import pytest

from src.services import process_manager, stream_service
from src.utils.cancellation import CancellationToken, PipelineCancelledError


async def _collect(response):
    lines = []
    async for chunk in response.body_iterator:
        lines.append(chunk)
    return lines


@pytest.mark.asyncio
async def test_stream_service_call_success():
    def func(*, cancel_token=None, on_line=None):
        on_line("hello")
        on_line("world")
        return "done"

    response = stream_service.stream_service_call(func)
    lines = await _collect(response)

    assert lines[0].startswith("data: [REQUEST_ID] ")
    assert "data: hello\n\n" in lines
    assert "data: world\n\n" in lines
    assert lines[-1] == "data: [PROCESS_EXITED] code=0\n\n"


@pytest.mark.asyncio
async def test_stream_service_call_exception():
    def func(*, cancel_token=None, on_line=None):
        raise ValueError("boom")

    response = stream_service.stream_service_call(func)
    lines = await _collect(response)

    assert any("[ERROR] boom" in line for line in lines)
    assert lines[-1] == "data: [PROCESS_EXITED] code=1\n\n"


@pytest.mark.asyncio
async def test_stream_service_call_cancellation():
    def func(*, cancel_token=None, on_line=None):
        cancel_token.cancel()
        cancel_token.check()

    response = stream_service.stream_service_call(func)
    lines = await _collect(response)

    assert lines[-1] == "data: [PROCESS_CANCELLED]\n\n"


@pytest.mark.asyncio
async def test_stream_service_call_registers_and_unregisters_process():
    def func(*, cancel_token=None, on_line=None):
        assert isinstance(cancel_token, CancellationToken)

    response = stream_service.stream_service_call(func)
    lines = await _collect(response)
    request_id = lines[0].split("[REQUEST_ID]")[1].strip().rstrip("\n")

    # After the stream completes, the process must be unregistered.
    assert process_manager.get_process(request_id) is None


@pytest.mark.asyncio
async def test_stream_service_call_cancel_via_process_manager():
    def func(*, cancel_token=None, on_line=None):
        for _ in range(500):
            if cancel_token.is_cancelled():
                break
            time.sleep(0.01)
        cancel_token.check()

    response = stream_service.stream_service_call(func)
    agen = response.body_iterator.__aiter__()

    first = await agen.__anext__()
    request_id = first.split("[REQUEST_ID]")[1].strip()
    process_manager.cancel_process(request_id)

    async def _collect_rest():
        lines = [first]
        async for chunk in agen:
            lines.append(chunk)
        return lines

    lines = await asyncio.wait_for(_collect_rest(), timeout=10)
    assert lines[-1] == "data: [PROCESS_CANCELLED]\n\n"


def test_pipeline_cancelled_error_is_exception():
    assert issubclass(PipelineCancelledError, Exception)
