from fastapi.testclient import TestClient

from src.review_server import app

client = TestClient(app)


def test_get_index():
    # Test index page rendering (FastAPI returns index.html)
    # The index page will look for templates and components.
    # If the index.html template and included files exist, it should succeed.
    response = client.get("/")
    assert response.status_code == 200
    assert "html" in response.headers["content-type"]


def test_api_config():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "novel_title" in data
    assert data["novel_title"] == "重天の調律師"


def test_list_available_models():
    # Since agy models might or might not be installed, the server has a fallback
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0
    # Fallback or active models should contain Gemini model types
    assert any("Gemini" in m for m in data["models"])
