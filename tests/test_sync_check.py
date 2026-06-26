from unittest.mock import MagicMock, patch

from src.sync_check import main


def test_sync_check_config_error(capsys):
    # Case: Config file not found or invalid
    with (
        patch("os.path.exists", return_value=False),
        patch("sys.exit"),
    ):
        main()
        captured = capsys.readouterr()
        # It prints diagnostics or error message
        assert "[ERROR]" in captured.out or "Diagnostics" in captured.out


def test_sync_check_diagnostics_success(tmp_path, capsys):
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
            return_value={
                "skills": [
                    {
                        "sources": [
                            {
                                "type": "google-drive",
                                "folder_id": "folder_id_123",
                                "auth_file": str(dummy_creds),
                            }
                        ]
                    }
                ]
            },
        ),
        patch(
            "src.utils.project_config.get_gdrive_config",
            return_value=("folder_id_123", str(dummy_creds)),
        ),
        patch("os.path.exists", return_value=True),
        patch(
            "src.sync_check.service_account.Credentials.from_service_account_file",
            return_value=mock_creds,
        ),
        patch("src.sync_check.build", return_value=mock_service),
    ):
        main()
        captured = capsys.readouterr()
        assert "[OK] Credentials file found." in captured.out
        assert "[OK] Found 1 files in folder:" in captured.out
