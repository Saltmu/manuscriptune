from unittest.mock import MagicMock, patch

from src.cli.sync_check import main
from src.utils.project_config import AppConfig


def test_sync_check_config_error(caplog):
    import logging

    # Case: Config file not found or invalid
    with (
        patch("os.path.exists", return_value=False),
        patch("sys.exit"),
        caplog.at_level(logging.ERROR),
    ):
        main()
        assert (
            "Could not find Google Drive configuration in antigravity.yaml"
            in caplog.text
        )


def test_sync_check_diagnostics_success(tmp_path, caplog):
    import logging

    # Mock credentials file existence
    dummy_creds = tmp_path / "service_account.json"
    dummy_creds.touch()

    # Mock service_account.Credentials and build
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_files = mock_service.files.return_value
    mock_list = mock_files.list.return_value
    mock_list.execute.return_value = {"files": [{"id": "file_1", "name": "Document"}]}

    with (
        patch(
            "src.utils.project_config.load_project_config",
            return_value=AppConfig(
                project={"name": "dummy"},
                agent={"name": "dummy"},
                google_drive={
                    "type": "google-drive",
                    "folder_id": "folder_id_123",
                    "auth_file": str(dummy_creds),
                },
            ),
        ),
        patch(
            "src.utils.project_config.get_gdrive_config",
            return_value=("folder_id_123", str(dummy_creds)),
        ),
        patch("os.path.exists", return_value=True),
        patch(
            "src.cli.sync_check.service_account.Credentials.from_service_account_file",
            return_value=mock_creds,
        ),
        patch("src.cli.sync_check.build", return_value=mock_service),
        caplog.at_level(logging.INFO),
    ):
        main()
        assert "Credentials file found." in caplog.text
        assert "Found 1 files in folder:" in caplog.text
