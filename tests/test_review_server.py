import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from src.review_server import app
from src.routes.api import WriteParams
from src.services import novel_service

client = TestClient(app, raise_server_exceptions=False)


def test_get_index():
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
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0
    assert any("Gemini" in m for m in data["models"])


def test_save_novel():
    os.makedirs("novels", exist_ok=True)
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
        if os.path.exists(f"{tmp_name}.bak"):
            os.remove(f"{tmp_name}.bak")


def test_backup_and_rollback():
    os.makedirs("novels", exist_ok=True)
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


def test_sync_status():
    response = client.get("/api/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data


def test_preview_novel():
    os.makedirs("novels", exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="novels") as tmp:
        tmp.write(b"Test preview content")
        tmp_name = tmp.name
        tmp_basename = os.path.basename(tmp_name)

    try:
        response = client.get(f"/api/preview?file={tmp_basename}")
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test preview content"
        assert data["filename"] == tmp_basename

        # Test 404
        response_404 = client.get("/api/preview?file=non_existent_file.txt")
        assert response_404.status_code == 404
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_select_file():
    os.makedirs("novels", exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="novels") as tmp:
        tmp.write(b"content")
        tmp_name = tmp.name
        tmp_basename = os.path.basename(tmp_name)

    try:
        response = client.post("/api/select", json={"novel_name": tmp_basename})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "novel_path" in data
        assert "yaml_path" in data
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_get_data():
    os.makedirs("novels", exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="novels") as tmp:
        tmp.write(b"Line 1\nLine 2")
        tmp_name = tmp.name
        tmp_basename = os.path.basename(tmp_name)

    try:
        response = client.get(f"/api/data?file={tmp_basename}")
        assert response.status_code == 200
        data = response.json()
        assert data["novel_filename"] == tmp_basename
        assert data["novel_lines"] == ["Line 1", "Line 2"]
        assert "findings" in data
        assert "has_backup" in data

        # Test empty input error handling (should return default empty values with 200 OK)
        response_empty = client.get("/api/data?file=")
        assert response_empty.status_code == 200
        data_empty = response_empty.json()
        assert data_empty["novel_filename"] == "ファイル未選択"
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


# --- 新規テスト: services/novel_service.py ---


def test_novel_service_resolve_paths_empty():
    with pytest.raises(Exception) as excinfo:
        novel_service.resolve_paths("")
    assert excinfo.value.status_code == 400


def test_novel_service_render_html_template_not_found():
    with pytest.raises(FileNotFoundError):
        novel_service.render_html_template("non_existent_template.html")


def test_novel_service_stream_process_output():
    res = novel_service.stream_process_output(["echo", "hello"])
    assert isinstance(res, StreamingResponse)
    assert res.media_type == "text/event-stream"


def test_novel_service_rollback_backup_not_found():
    with pytest.raises(Exception) as excinfo:
        novel_service.rollback_backup("non_existent.txt", "non_existent.yaml")
    assert excinfo.value.status_code == 404


def test_novel_service_rollback_backup_yaml_only(tmp_path):
    novel_path = tmp_path / "novel.txt"
    yaml_path = tmp_path / "novel_findings.yaml"
    novel_bak = tmp_path / "novel.txt.bak"

    novel_bak.write_text("backup text", encoding="utf-8")
    yaml_path.write_text(
        "findings:\n  - id: INT-001\n    apply_status: success\n    apply_result: done",
        encoding="utf-8",
    )

    res = novel_service.rollback_backup(str(novel_path), str(yaml_path))
    assert res["status"] == "success"

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        assert data["findings"][0]["apply_status"] is None
        assert data["findings"][0]["apply_result"] is None


def test_novel_service_rollback_backup_exception(tmp_path):
    novel_path = tmp_path / "exists.txt"
    yaml_path = tmp_path / "exists.yaml"
    novel_bak = tmp_path / "exists.txt.bak"
    novel_bak.touch()

    with patch("shutil.copy2", side_effect=Exception("Permission denied")):
        with pytest.raises(Exception) as excinfo:
            novel_service.rollback_backup(str(novel_path), str(yaml_path))
        assert excinfo.value.status_code == 500


def test_novel_service_build_writer_cmd():
    params = WriteParams(
        episode="1",
        novel_title="Title",
        policy_global="global.txt",
        policy_chapter="chapter.txt",
        character="char.txt",
        plot="plot.txt",
        model="model-name",
        step_by_step=True,
        self_check=True,
    )
    cmd = novel_service.build_writer_cmd(params)
    assert "--episode" in cmd
    assert "1" in cmd
    assert "--title" in cmd
    assert "Title" in cmd
    assert "--policy-global" in cmd
    assert "data/sources/global.txt" in cmd
    assert "--policy-chapter" in cmd
    assert "data/sources/chapter.txt" in cmd
    assert "--character" in cmd
    assert "data/sources/char.txt" in cmd
    assert "--plot-file" in cmd
    assert "data/sources/plot.txt" in cmd
    assert "--step-by-step" in cmd
    assert "--self-check" in cmd
    assert "model-name" in cmd


def test_novel_service_shutdown_server():
    with patch("os.kill") as mock_kill:
        novel_service.shutdown_server()
        mock_kill.assert_called_once_with(os.getpid(), signal.SIGINT)


# --- 新規テスト: routes/api.py ---


def test_routes_api_save_novel_guardrail():
    with patch(
        "src.services.novel_service.resolve_paths",
        return_value=("data/sources/some_source.txt", "some.yaml"),
    ):
        response = client.post(
            "/api/save_novel",
            json={"novel_name": "some_source.txt", "content": "Updated Content"},
        )
        assert response.status_code == 403
        assert "strictly prohibited" in response.json()["detail"]


def test_routes_api_save_novel_exception():
    with (
        patch(
            "src.services.novel_service.resolve_paths",
            return_value=("novels/dummy.txt", "dummy.yaml"),
        ),
        patch("builtins.open", side_effect=Exception("IO Error")),
    ):
        response = client.post(
            "/api/save_novel",
            json={"novel_name": "dummy.txt", "content": "Updated Content"},
        )
        assert response.status_code == 500


def test_routes_api_save_findings_success(tmp_path):
    yaml_path = tmp_path / "dummy_findings.yaml"
    with patch(
        "src.services.novel_service.resolve_paths",
        return_value=("dummy.txt", str(yaml_path)),
    ):
        response = client.post(
            "/api/save",
            json={
                "novel_name": "dummy.txt",
                "findings": [
                    {
                        "id": "INT-001",
                        "location": "1",
                        "original": "orig",
                        "category": "cat",
                        "severity": "high",
                        "analysis": "anal",
                        "suggestion": "sugg",
                        "accepted": "y",
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert yaml_path.exists()


def test_routes_api_save_findings_no_yaml():
    with patch(
        "src.services.novel_service.resolve_paths", return_value=("dummy.txt", None)
    ):
        response = client.post(
            "/api/save", json={"novel_name": "dummy.txt", "findings": []}
        )
        assert response.status_code == 400


def test_routes_api_save_findings_exception():
    with (
        patch(
            "src.services.novel_service.resolve_paths",
            return_value=("dummy.txt", "dummy_findings.yaml"),
        ),
        patch("os.makedirs", side_effect=Exception("Failed")),
    ):
        response = client.post(
            "/api/save", json={"novel_name": "dummy.txt", "findings": []}
        )
        assert response.status_code == 500


def test_routes_api_create_backup_exception():
    with (
        patch(
            "src.services.novel_service.resolve_paths",
            return_value=("dummy.txt", "dummy.yaml"),
        ),
        patch("os.path.exists", return_value=True),
        patch("shutil.copy2", side_effect=Exception("Error")),
    ):
        response = client.post("/api/backup?file=dummy.txt")
        assert response.status_code == 500


def test_routes_api_stream_apply():
    mock_streaming = StreamingResponse(
        iter(["data: line\n\n"]), media_type="text/event-stream"
    )
    with patch(
        "src.services.novel_service.stream_process_output", return_value=mock_streaming
    ) as mock_stream:
        response = client.get("/api/stream/apply?file=dummy.txt")
        assert response.status_code == 200
        assert response.text == "data: line\n\n"
        mock_stream.assert_called_once()


def test_routes_api_stream_apply_exception():
    with patch(
        "src.services.novel_service.resolve_paths", side_effect=Exception("Error")
    ):
        response = client.get("/api/stream/apply?file=dummy.txt")
        assert response.status_code == 500


def test_routes_api_stream_sync():
    mock_streaming = StreamingResponse(
        iter(["data: line\n\n"]), media_type="text/event-stream"
    )
    with patch(
        "src.services.novel_service.stream_process_output", return_value=mock_streaming
    ) as mock_stream:
        response = client.get("/api/stream/sync")
        assert response.status_code == 200
        mock_stream.assert_called_once()


def test_routes_api_stream_review():
    mock_streaming = StreamingResponse(
        iter(["data: line\n\n"]), media_type="text/event-stream"
    )
    with (
        patch("os.path.exists", return_value=True),
        patch(
            "src.services.novel_service.stream_process_output",
            return_value=mock_streaming,
        ) as mock_stream,
    ):
        response = client.get("/api/stream/review?file=dummy.txt&model=Gemini")
        assert response.status_code == 200
        mock_stream.assert_called_once()


def test_routes_api_stream_review_not_found():
    with patch("os.path.exists", return_value=False):
        response = client.get("/api/stream/review?file=dummy.txt")
        assert response.status_code == 404


def test_routes_api_stream_write():
    mock_streaming = StreamingResponse(
        iter(["data: line\n\n"]), media_type="text/event-stream"
    )
    with patch(
        "src.services.novel_service.stream_process_output", return_value=mock_streaming
    ) as mock_stream:
        response = client.get("/api/stream/write?episode=1")
        assert response.status_code == 200
        mock_stream.assert_called_once()


def test_routes_api_shutdown():
    response = client.post("/api/shutdown")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_routes_api_novels_empty():
    with patch("pathlib.Path.exists", return_value=False):
        response = client.get("/api/novels")
        assert response.status_code == 200
        assert response.json() == {"novels": []}


def test_routes_api_novel_yaml_exception(tmp_path):
    novel_path = tmp_path / "dummy.txt"
    yaml_path = tmp_path / "dummy_findings.yaml"
    novel_path.write_text("novel content", encoding="utf-8")
    yaml_path.write_text("invalid_yaml: [", encoding="utf-8")

    with patch(
        "src.services.novel_service.resolve_paths",
        return_value=(str(novel_path), str(yaml_path)),
    ):
        response = client.get(f"/api/novel?file={os.path.basename(novel_path)}")
        assert response.status_code == 200
        data = response.json()
        assert data["findings"] == []


def test_routes_api_novel_not_found():
    with patch(
        "src.services.novel_service.resolve_paths",
        return_value=("non_existent.txt", None),
    ):
        response = client.get("/api/novel?file=non_existent.txt")
        assert response.status_code == 404


def test_routes_api_get_data_404():
    with (
        patch(
            "src.services.novel_service.resolve_paths",
            return_value=("non_existent.txt", None),
        ),
        patch("os.path.exists", return_value=False),
    ):
        response = client.get("/api/data?file=non_existent.txt")
        assert response.status_code == 404


def test_routes_api_get_data_yaml_exception(tmp_path):
    novel_path = tmp_path / "dummy.txt"
    yaml_path = tmp_path / "dummy_findings.yaml"
    novel_path.write_text("line1\nline2", encoding="utf-8")
    yaml_path.write_text("invalid_yaml: [", encoding="utf-8")

    with (
        patch(
            "src.services.novel_service.resolve_paths",
            return_value=(str(novel_path), str(yaml_path)),
        ),
        patch("os.path.exists", side_effect=[True, True]),
    ):
        response = client.get(f"/api/data?file={os.path.basename(novel_path)}")
        assert response.status_code == 500


def test_routes_api_preview_novel_exception():
    with (
        patch("os.path.exists", return_value=True),
        patch("builtins.open", side_effect=Exception("Read Error")),
    ):
        response = client.get("/api/preview?file=dummy.txt")
        assert response.status_code == 500


def test_routes_api_get_index_exception():
    with patch(
        "src.services.novel_service.render_html_template",
        side_effect=Exception("Render error"),
    ):
        response = client.get("/")
        assert response.status_code == 500


def test_routes_api_select_file_exception():
    with patch(
        "src.services.novel_service.resolve_paths",
        side_effect=Exception("General error"),
    ):
        response = client.post("/api/select", json={"novel_name": "dummy.txt"})
        assert response.status_code == 500


def test_routes_api_get_write_prompt():
    from unittest.mock import AsyncMock

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Generated Prompt Content", b"")
    mock_process.returncode = 0

    with patch(
        "asyncio.create_subprocess_exec", return_value=mock_process
    ) as mock_exec:
        response = client.get(
            "/api/write/prompt?episode=%E7%AC%AC1%E8%A9%B1&novel_title=TestTitle"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prompt"] == "Generated Prompt Content"

        mock_exec.assert_called_once()
        cmd_arg = mock_exec.call_args
        # The first argument tuple to create_subprocess_exec has command parts
        assert any("--prompt-only" in str(arg) for arg in cmd_arg[0])


def test_routes_api_list_plots(tmp_path):
    sources_dir = Path("data/sources")
    os.makedirs(sources_dir, exist_ok=True)

    mock_plot = sources_dir / "04_1_01_プロット.txt"
    mock_plot.write_text("プロットの中身", encoding="utf-8")

    try:
        response = client.get("/api/plots")
        assert response.status_code == 200
        data = response.json()
        assert "plots" in data
        assert any(p["name"] == "04_1_01_プロット.txt" for p in data["plots"])
    finally:
        if mock_plot.exists():
            mock_plot.unlink()


def test_routes_api_get_plot_not_found():
    response = client.get("/api/plot?file=non_existent_plot.txt")
    assert response.status_code == 404


def test_routes_api_get_plot_success():
    sources_dir = Path("data/sources")
    os.makedirs(sources_dir, exist_ok=True)

    mock_plot = sources_dir / "test_get_plot.txt"
    mock_plot.write_text("プロットテスト本文", encoding="utf-8")

    try:
        response = client.get("/api/plot?file=test_get_plot.txt")
        assert response.status_code == 200
        data = response.json()
        assert data["plot_name"] == "test_get_plot.txt"
        assert data["content"] == "プロットテスト本文"
        assert "findings" in data
    finally:
        if mock_plot.exists():
            mock_plot.unlink()


def test_routes_api_stream_plot_review_not_found():
    response = client.get("/api/stream/plot_review?file=non_existent.txt")
    assert response.status_code == 404


def test_routes_api_stream_plot_review_success():
    sources_dir = Path("data/sources")
    os.makedirs(sources_dir, exist_ok=True)

    mock_plot = sources_dir / "test_stream_plot.txt"
    mock_plot.write_text("プロットテスト本文", encoding="utf-8")

    try:
        with patch("src.services.novel_service.stream_process_output") as mock_stream:
            mock_stream.return_value = StreamingResponse(iter([b"data: success\n\n"]))
            response = client.get(
                "/api/stream/plot_review?file=test_stream_plot.txt&model=test-model"
            )
            assert response.status_code == 200
            assert mock_stream.called
    finally:
        if mock_plot.exists():
            mock_plot.unlink()
