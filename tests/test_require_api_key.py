import pytest
from fastapi.testclient import TestClient

from src.cli.review_server import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api_key():
    token = "test-secret-token"
    app.state.api_key = token
    yield token
    del app.state.api_key


def test_no_key_configured_allows_request():
    # app.state.api_key が未設定(main()を経由しないテスト実行時)の場合は認証を無効化する
    assert not hasattr(app.state, "api_key")
    response = client.get("/api/cancel?request_id=missing")
    assert response.status_code == 404  # not 401


def test_protected_endpoint_rejects_missing_token(api_key):
    response = client.post("/api/shutdown")
    assert response.status_code == 401


def test_protected_endpoint_rejects_wrong_bearer_token(api_key):
    response = client.post(
        "/api/shutdown", headers={"Authorization": f"Bearer wrong-{api_key}"}
    )
    assert response.status_code == 401


def test_protected_endpoint_accepts_bearer_token(api_key):
    response = client.get(
        "/api/cancel?request_id=missing",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 404  # reached the handler, just no such process


def test_protected_sse_endpoint_accepts_query_param_token(api_key):
    # EventSourceはカスタムヘッダーを送れないため、クエリパラメータでも認証できる
    response = client.get(f"/api/cancel?request_id=missing&token={api_key}")
    assert response.status_code == 404


def test_unprotected_endpoint_ignores_missing_token(api_key):
    response = client.get("/api/novels")
    assert response.status_code == 200
