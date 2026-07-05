import threading


class PipelineCancelledError(Exception):
    """協調的キャンセル: フェーズ境界でCancellationTokenがセットされていた場合に送出する。"""


class CancellationToken:
    """スレッド越しに安全に共有できるキャンセルフラグ。

    subprocessと違いPythonスレッドは強制終了できないため、
    サービス側の処理はフェーズの境界ごとに check() を呼び、
    キャンセル済みなら PipelineCancelledError を送出して協調的に中断する。
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise PipelineCancelledError()
