"""
プロセス管理システム
実行中のストリーミングプロセス（LLM処理等）を管理し、キャンセル機能を提供する。
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class Cancellable(Protocol):
    """asyncio.Task(サブプロセス方式)とCancellationToken(インプロセス方式)の両方を
    キャンセル対象として扱えるようにする最小限のインターフェース。"""

    def cancel(self) -> object: ...


# グローバルな実行中プロセス管理
_active_processes: dict[str, Cancellable] = {}


def register_process(request_id: str, task: Cancellable) -> None:
    """
    プロセスを登録する。

    Args:
        request_id: リクエスト一意ID
        task: 管理対象のオブジェクト(asyncio.Task または CancellationToken)
    """
    _active_processes[request_id] = task
    logger.debug(f"Process registered: {request_id}")


def unregister_process(request_id: str) -> None:
    """
    プロセスの登録を解除する。

    Args:
        request_id: リクエスト一意ID
    """
    if request_id in _active_processes:
        del _active_processes[request_id]
        logger.debug(f"Process unregistered: {request_id}")


def get_process(request_id: str) -> Cancellable | None:
    """
    登録済みプロセスを取得する。

    Args:
        request_id: リクエスト一意ID

    Returns:
        Cancellable または None（登録されていない場合）
    """
    return _active_processes.get(request_id)


def get_active_processes() -> dict[str, Cancellable]:
    """
    全ての登録済みプロセスを取得する。

    Returns:
        {request_id: Task} の辞書
    """
    return _active_processes.copy()


def cancel_process(request_id: str) -> bool:
    """
    プロセスをキャンセルする。

    Args:
        request_id: リクエスト一意ID

    Returns:
        True: キャンセル成功
        False: プロセス未登録またはキャンセル失敗
    """
    task = get_process(request_id)
    if task is None:
        logger.warning(f"Process not found for cancellation: {request_id}")
        return False

    try:
        task.cancel()
        unregister_process(request_id)
        logger.info(f"Process cancelled: {request_id}")
        return True
    except Exception as e:
        logger.error(f"Error cancelling process {request_id}: {e}")
        return False


def clear_all_processes() -> None:
    """
    全プロセスをクリア（テスト用）。
    """
    _active_processes.clear()
    logger.debug("All processes cleared")
