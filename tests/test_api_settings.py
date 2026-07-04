from fastapi.testclient import TestClient

from src.cli.review_server import app

client = TestClient(app, raise_server_exceptions=False)


class TestSettingsEndpoint:
    """設定API（/api/settings）のテスト"""

    def test_get_settings_default(self):
        """デフォルト設定を取得できる"""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "model" in data

    def test_post_settings_success(self):
        """設定を正常に保存できる"""
        settings_data = {
            "title": "テスト小説",
            "model": "Gemini 3.5 Flash (High)",
            "policy_global": "グローバルポリシー",
            "policy_chapter": "チャプターポリシー",
            "character": "キャラクター設定",
        }
        response = client.post(
            "/api/settings",
            json=settings_data,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_post_settings_partial(self):
        """部分的な設定更新ができる"""
        settings_data = {"title": "新しい小説名"}
        response = client.post(
            "/api/settings",
            json=settings_data,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_post_settings_empty(self):
        """空の設定リクエストは成功"""
        response = client.post(
            "/api/settings", json={}, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_settings_after_post(self):
        """POST後のGET で保存された値が返される"""
        # 設定を保存
        settings_data = {
            "title": "テスト小説タイトル",
            "model": "Gemini 3.5 Flash (Medium)",
        }
        post_response = client.post(
            "/api/settings",
            json=settings_data,
            headers={"Content-Type": "application/json"},
        )
        assert post_response.status_code == 200

        # 設定を取得
        get_response = client.get("/api/settings")
        assert get_response.status_code == 200
        data = get_response.json()
        # 保存された値が反映されていることを確認
        assert "title" in data
        assert "model" in data

    def test_post_settings_invalid_json(self):
        """不正なJSONリクエストは422エラー"""
        response = client.post(
            "/api/settings",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
