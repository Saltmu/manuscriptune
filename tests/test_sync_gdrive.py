import os
import time
from unittest.mock import MagicMock, patch

from src.sync_gdrive import (
    _check_lock_and_cache,
    _download_gdrive_file,
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
