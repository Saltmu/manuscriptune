"""CLIサブプロセスを介さず、サービス層の関数呼び出しをSSEでストリーミングするための橋渡し。

novel_service.stream_process_output と同じワイヤープロトコル
([REQUEST_ID] / 生ログ行 / [PROCESS_EXITED] code=N / [PROCESS_CANCELLED]) を維持することで、
フロントエンド(frontend/src/utils.js の startEventStream)側の変更を不要にする。
"""

import asyncio
import contextvars
import logging
import uuid
from collections.abc import Callable
from typing import Any

from fastapi.responses import StreamingResponse

from src.services import process_manager
from src.utils.cancellation import CancellationToken, PipelineCancelledError

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_request_id_ctx", default=""
)


class _QueueLogHandler(logging.Handler):
    """特定のrequest_idに紐づくログ記録だけをasyncio.Queueへ転送するハンドラ。

    同時に複数のstream_service_callが動いていても、コンテキスト変数でフィルタする
    ことでログ行が混ざらないようにする。
    """

    def __init__(
        self,
        queue: "asyncio.Queue[str]",
        loop: asyncio.AbstractEventLoop,
        request_id: str,
    ) -> None:
        super().__init__()
        self.queue = queue
        self.loop = loop
        self.request_id = request_id
        self.setFormatter(logging.Formatter("%(message)s"))

    def filter(self, record: logging.LogRecord) -> bool:
        return _request_id_ctx.get() == self.request_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.loop.call_soon_threadsafe(self.queue.put_nowait, message)
        except Exception:
            self.handleError(record)


def stream_service_call(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> StreamingResponse:
    """同期のサービス関数をワーカースレッドで実行し、進捗をSSEとして中継する。

    func は cancel_token: CancellationToken と on_line: Callable[[str], None] を
    キーワード引数として受け取れる必要がある(未使用でも構わない)。
    """
    request_id = str(uuid.uuid4())

    async def event_generator():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()
        token = CancellationToken()

        # 現在の(このリクエスト専用の)コンテキストにセットしておくことで、
        # asyncio.to_thread がコピーするコンテキストにも引き継がれる。
        _request_id_ctx.set(request_id)

        handler = _QueueLogHandler(queue, loop, request_id)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        process_manager.register_process(request_id, token)

        yield f"data: [REQUEST_ID] {request_id}\n\n"

        def on_line(line: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, line)

        def _run() -> Any:
            return func(*args, cancel_token=token, on_line=on_line, **kwargs)

        task = asyncio.create_task(asyncio.to_thread(_run))
        try:
            while not task.done():
                get_task: asyncio.Task[str] = asyncio.ensure_future(queue.get())
                done, _pending = await asyncio.wait(
                    {task, get_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if get_task in done:
                    yield f"data: {get_task.result()}\n\n"
                else:
                    get_task.cancel()

            while not queue.empty():
                yield f"data: {queue.get_nowait()}\n\n"

            exc = task.exception()
            if isinstance(exc, PipelineCancelledError):
                yield "data: [PROCESS_CANCELLED]\n\n"
            elif exc is not None:
                yield f"data: [ERROR] {exc}\n\n"
                yield "data: [PROCESS_EXITED] code=1\n\n"
            else:
                yield "data: [PROCESS_EXITED] code=0\n\n"
        finally:
            root_logger.removeHandler(handler)
            process_manager.unregister_process(request_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
