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


def test_save_novel():
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="novels") as tmp:
        tmp.write(b"Original Content")
        tmp_name = tmp.name
        tmp_basename = os.path.basename(tmp_name)

    try:
        response = client.post(
            "/api/save_novel",
            json={"novel_name": tmp_basename, "content": "Updated Content"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        with open(tmp_name, encoding="utf-8") as f:
            assert f.read() == "Updated Content"
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_backup_and_rollback():
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="novels") as tmp:
        tmp.write(b"Original content for backup")
        tmp_name = tmp.name
        tmp_basename = os.path.basename(tmp_name)

    try:
        # Create backup
        response = client.post(f"/api/backup?file={tmp_basename}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify backup exists
        bak_name = f"{tmp_name}.bak"
        assert os.path.exists(bak_name)
        with open(bak_name, encoding="utf-8") as f:
            assert f.read() == "Original content for backup"

        # Change original file
        with open(tmp_name, "w", encoding="utf-8") as f:
            f.write("Modified content")

        # Rollback
        response = client.post(f"/api/rollback?file={tmp_basename}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify original file content is restored
        with open(tmp_name, encoding="utf-8") as f:
            assert f.read() == "Original content for backup"

    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        if os.path.exists(f"{tmp_name}.bak"):
            os.remove(f"{tmp_name}.bak")
