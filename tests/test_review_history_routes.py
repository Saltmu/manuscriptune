from unittest.mock import patch

from fastapi.testclient import TestClient

from src.cli.review_server import app

client = TestClient(app, raise_server_exceptions=False)


class TestListReviewHistoryEndpoint:
    """一覧取得API（/api/review_history）のテスト"""

    def test_list_returns_versions(self):
        fake_versions = [
            {
                "version": "v1",
                "version_number": 1,
                "mtime": 123.0,
                "findings_count": 2,
                "has_report": True,
            },
            {
                "version": "v2",
                "version_number": 2,
                "mtime": 456.0,
                "findings_count": 0,
                "has_report": False,
            },
        ]
        with patch(
            "src.routes.review_history.review_history_service.list_history_versions",
            return_value=fake_versions,
        ) as mock_list:
            response = client.get("/api/review_history", params={"file": "1_12.txt"})

        assert response.status_code == 200
        data = response.json()
        assert [v["version"] for v in data["versions"]] == ["v1", "v2"]
        mock_list.assert_called_once_with("1_12")

    def test_list_missing_file_param_is_422(self):
        response = client.get("/api/review_history")
        assert response.status_code == 422

    def test_list_no_history_returns_empty(self):
        with patch(
            "src.routes.review_history.review_history_service.list_history_versions",
            return_value=[],
        ):
            response = client.get("/api/review_history", params={"file": "no_hist"})

        assert response.status_code == 200
        assert response.json() == {"versions": []}


class TestReviewHistoryDetailEndpoint:
    """詳細取得API（/api/review_history/detail）のテスト"""

    def test_detail_returns_report_and_findings(self):
        fake_detail = {
            "version": "v1",
            "report": "# Report v1",
            "findings": [{"id": "F-1"}],
        }
        with patch(
            "src.routes.review_history.review_history_service.get_history_version_detail",
            return_value=fake_detail,
        ) as mock_detail:
            response = client.get(
                "/api/review_history/detail",
                params={"file": "1_12.txt", "version": "v1"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v1"
        assert data["report"] == "# Report v1"
        assert data["findings"] == [{"id": "F-1"}]
        mock_detail.assert_called_once_with("1_12", "v1")

    def test_detail_not_found_returns_404(self):
        with patch(
            "src.routes.review_history.review_history_service.get_history_version_detail",
            side_effect=FileNotFoundError("not found"),
        ):
            response = client.get(
                "/api/review_history/detail",
                params={"file": "1_12.txt", "version": "v99"},
            )

        assert response.status_code == 404

    def test_detail_missing_params_is_422(self):
        response = client.get("/api/review_history/detail", params={"file": "1_12.txt"})
        assert response.status_code == 422
