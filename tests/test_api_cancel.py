import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.cli.review_server import app
from src.services import process_manager

client = TestClient(app, raise_server_exceptions=False)


class TestProcessManager:
    """プロセス管理システムのテスト"""

    def test_register_process(self):
        """プロセス登録が正常に行われることを確認"""
        request_id = str(uuid.uuid4())
        mock_task = MagicMock()

        process_manager.register_process(request_id, mock_task)

        assert request_id in process_manager.get_active_processes()
        assert process_manager.get_process(request_id) == mock_task

    def test_unregister_process(self):
        """プロセス登録解除が正常に行われることを確認"""
        request_id = str(uuid.uuid4())
        mock_task = MagicMock()

        process_manager.register_process(request_id, mock_task)
        assert request_id in process_manager.get_active_processes()

        process_manager.unregister_process(request_id)
        assert request_id not in process_manager.get_active_processes()

    def test_get_nonexistent_process(self):
        """存在しないプロセスを取得時、Noneを返す"""
        request_id = str(uuid.uuid4())
        assert process_manager.get_process(request_id) is None

    def test_cancel_nonexistent_process(self):
        """存在しないプロセスをキャンセルしてもエラーが出ない"""
        request_id = str(uuid.uuid4())
        result = process_manager.cancel_process(request_id)
        assert result is False  # キャンセル対象なし


class TestCancelEndpoint:
    """キャンセルエンドポイント（/api/cancel）のテスト"""

    def test_cancel_nonexistent_request(self):
        """存在しないリクエストIDでキャンセルした場合、404を返す"""
        request_id = str(uuid.uuid4())
        response = client.get(f"/api/cancel?request_id={request_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Process not found"

    def test_cancel_existing_process(self):
        """実行中のプロセスが正常にキャンセルされることを確認"""
        request_id = str(uuid.uuid4())

        # モックタスク作成
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()

        # プロセスを登録
        process_manager.register_process(request_id, mock_task)

        # キャンセルリクエスト
        response = client.get(f"/api/cancel?request_id={request_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

        # プロセスが登録解除されていることを確認
        assert process_manager.get_process(request_id) is None

    def test_cancel_missing_request_id_parameter(self):
        """request_idクエリパラメータが省略された場合、422を返す"""
        response = client.get("/api/cancel")
        assert response.status_code == 422  # Validation error


class TestStreamProcessWithCancel:
    """ストリーミングプロセスとキャンセル機能の統合テスト"""

    @pytest.mark.asyncio
    async def test_stream_process_generates_request_id(self):
        """ストリーミングプロセスが request_id を生成・返却すること"""
        # このテストは実装後に詳細化
        pass

    def test_cancel_during_streaming(self):
        """ストリーミング中のプロセスがキャンセル可能であること"""
        # このテストは実装後に詳細化
        pass
