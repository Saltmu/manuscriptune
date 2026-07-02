import os
import time
from unittest.mock import MagicMock, patch

import pytest

from src.sync_gdrive import (
    _check_lock_and_cache,
    _download_gdrive_file,
    main,
)


def test_check_lock_and_cache(tmp_path):
    cache_file = str(tmp_path / ".sync_cache")
    lock_file = str(tmp_path / ".sync.lock")
    cache_duration = 60  # 60 seconds

    # Case 1: Neither cache nor lock exists - should proceed
    assert _check_lock_and_cache(cache_file, lock_file, cache_duration) is True

    # Case 2: Lock exists - should skip
    with open(lock_file, "w") as f:
        f.write("12345")
    assert _check_lock_and_cache(cache_file, lock_file, cache_duration) is False
    os.remove(lock_file)

    # Case 3: Cache is fresh - should skip
    with open(cache_file, "w") as f:
        f.write(str(time.time()))
    assert _check_lock_and_cache(cache_file, lock_file, cache_duration) is False

    # Case 4: Cache is expired - should proceed
    expired_time = time.time() - 100
    with open(cache_file, "w") as f:
        f.write(str(expired_time))
    os.utime(cache_file, (expired_time, expired_time))  # set modified time to past
    assert _check_lock_and_cache(cache_file, lock_file, cache_duration) is True


def test_download_gdrive_file_document(tmp_path):
    # Mock drive service
    mock_service = MagicMock()
    mock_files = mock_service.files.return_value

    # Mock media download
    mock_media = MagicMock()
    mock_media.next_chunk.return_value = (None, True)  # completed

    item = {
        "id": "doc_id_123",
        "name": "01_テスト小説",
        "mimeType": "application/vnd.google-apps.document",
    }

    with patch("src.sync_gdrive.MediaIoBaseDownload", return_value=mock_media):
        _download_gdrive_file(mock_service, item, str(tmp_path))

    # Verify that file export was requested as text/plain and written to disk
    mock_files.export_media.assert_called_once_with(
        fileId="doc_id_123", mimeType="text/plain"
    )
    assert os.path.exists(tmp_path / "01_テスト小説.txt")


def test_download_gdrive_file_normal(tmp_path):
    mock_service = MagicMock()
    mock_files = mock_service.files.return_value

    mock_media = MagicMock()
    mock_media.next_chunk.return_value = (None, True)

    item = {
        "id": "file_id_456",
        "name": "image.png",
        "mimeType": "image/png",
    }

    with patch("src.sync_gdrive.MediaIoBaseDownload", return_value=mock_media):
        _download_gdrive_file(mock_service, item, str(tmp_path))

    mock_files.get_media.assert_called_once_with(fileId="file_id_456")
    assert os.path.exists(tmp_path / "image.png")


def test_download_gdrive_file_skips(tmp_path):
    mock_service = MagicMock()

    # folder skip
    item_folder = {
        "id": "folder_id",
        "name": "SubFolder",
        "mimeType": "application/vnd.google-apps.folder",
    }
    _download_gdrive_file(mock_service, item_folder, str(tmp_path))
    assert not os.path.exists(tmp_path / "SubFolder")

    # unsupported google workspace file skip
    item_unsupported = {
        "id": "sheet_id",
        "name": "Spreadsheet",
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    _download_gdrive_file(mock_service, item_unsupported, str(tmp_path))
    assert not os.path.exists(tmp_path / "Spreadsheet")


@patch("src.sync_gdrive.build")
@patch("src.sync_gdrive.service_account.Credentials.from_service_account_file")
@patch("src.sync_gdrive.project_config")
@patch("src.sync_gdrive._check_lock_and_cache", return_value=True)
def test_main_success(mock_check, mock_config, mock_creds, mock_build, tmp_path):
    mock_config.load_project_config.return_value = {}
    mock_config.get_gdrive_config.return_value = (
        "folder_123",
        "./credentials/creds.json",
    )

    mock_service = MagicMock()
    mock_build.return_value = mock_service

    # Correct mock definition to avoid calling the non-existent fields() method
    mock_service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "doc_1",
                "name": "doc1",
                "mimeType": "application/vnd.google-apps.document",
            }
        ]
    }

    with (
        patch("src.sync_gdrive.os.path.dirname", return_value=str(tmp_path)),
        patch("src.sync_gdrive._download_gdrive_file") as mock_download,
    ):
        main()
        mock_download.assert_called_once()


def test_main_skipped_by_lock():
    with (
        patch("src.sync_gdrive._check_lock_and_cache", return_value=False),
        patch("src.sync_gdrive.project_config") as mock_config,
    ):
        main()
        mock_config.load_project_config.assert_not_called()


def test_main_no_config():
    with (
        patch("src.sync_gdrive._check_lock_and_cache", return_value=True),
        patch("src.sync_gdrive.project_config") as mock_config,
        patch("src.sync_gdrive.os.path.dirname", return_value="/dummy"),
    ):
        mock_config.load_project_config.return_value = {}
        mock_config.get_gdrive_config.return_value = (None, None)

        with patch("src.sync_gdrive.build") as mock_build:
            main()
            mock_build.assert_not_called()


@patch("src.sync_gdrive.build")
@patch("src.sync_gdrive.service_account.Credentials.from_service_account_file")
@patch("src.sync_gdrive.project_config")
@patch("src.sync_gdrive._check_lock_and_cache", return_value=True)
def test_main_failure_writes_status_yaml(
    mock_check, mock_config, mock_creds, mock_build, tmp_path
):
    import yaml

    mock_config.load_project_config.return_value = {}
    mock_config.get_gdrive_config.return_value = (
        "folder_123",
        "./credentials/creds.json",
    )

    mock_build.side_effect = Exception("Google Drive API connection failed")

    with (
        patch("src.sync_gdrive.os.path.dirname", return_value=str(tmp_path)),
    ):
        with pytest.raises(Exception, match="Google Drive API connection failed"):
            main()

        status_yaml = tmp_path / "data/sources/sync_status.yaml"
        assert status_yaml.exists()

        with open(status_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert "_metadata" in data
            assert data["_metadata"]["fallback_mode"] is True
            assert data["_metadata"]["completeness"] == "low"
            assert "connection failed" in data["_metadata"]["reason"]
