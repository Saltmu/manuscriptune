from fastapi.testclient import TestClient

from src.cli.review_server import app

client = TestClient(app, raise_server_exceptions=False)


def test_no_origin_or_referer_allowed():
    response = client.get("/api/config")
    assert response.status_code == 200


def test_same_origin_allowed():
    response = client.get("/api/config", headers={"origin": "http://testserver"})
    assert response.status_code == 200


def test_cross_origin_get_rejected():
    response = client.get("/api/config", headers={"origin": "https://evil.example.com"})
    assert response.status_code == 403


def test_cross_origin_post_rejected():
    response = client.post(
        "/api/settings",
        json={},
        headers={"origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
