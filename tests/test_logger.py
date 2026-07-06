import logging
import os
import shutil
import tempfile
from unittest.mock import patch

import pytest

from src.utils.logger import get_logger
from src.utils.project_config import AppConfig


@pytest.fixture
def temp_log_dir():
    # テスト用の一時ディレクトリを作成
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # テスト後に削除
    shutil.rmtree(temp_dir)


def test_get_logger_returns_logger():
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logger_creates_directory_and_file(temp_log_dir):
    log_file_path = os.path.join(temp_log_dir, "test_app.log")

    mock_config = AppConfig(
        project={"name": "dummy"},
        agent={"name": "dummy"},
        logging={
            "level": "DEBUG",
            "dir": temp_log_dir,
            "filename": "test_app.log",
            "max_bytes": 1024,
            "backup_count": 5,
        },
    )

    # load_project_config をモックして一時ディレクトリを使うようにする
    with patch("src.utils.logger.load_project_config", return_value=mock_config):
        # loggerの再初期化のため、_initialized フラグをリセットする
        import src.utils.logger

        src.utils.logger._initialized = False

        logger = get_logger("test_dir_creation")
        logger.info("Test log entry")

        # ログファイルが作成されたか確認
        assert os.path.exists(log_file_path)
        with open(log_file_path, encoding="utf-8") as f:
            content = f.read()
            assert "Test log entry" in content
            assert "[INFO]" in content
            assert "[test_dir_creation]" in content


def test_logger_rotation_and_generations(temp_log_dir):
    log_filename = "rotation_test.log"
    log_file_path = os.path.join(temp_log_dir, log_filename)

    # ローテーションを発生させるため、max_bytes を極小(50バイト)に設定
    mock_config = AppConfig(
        project={"name": "dummy"},
        agent={"name": "dummy"},
        logging={
            "level": "DEBUG",
            "dir": temp_log_dir,
            "filename": log_filename,
            "max_bytes": 50,
            "backup_count": 5,
        },
    )

    with patch("src.utils.logger.load_project_config", return_value=mock_config):
        import src.utils.logger

        src.utils.logger._initialized = False

        logger = get_logger("test_rotation")

        # 大量の長いログを書き込んでローテーションを発生させる
        # 1行あたり約30バイト + タイムスタンプなどのフォーマット部分が加わるため、1行で50バイトを超える
        for i in range(20):
            logger.debug(
                f"Log message number {i:02d} - writing enough data to force rotation"
            )

        # ログファイルが存在することを確認
        assert os.path.exists(log_file_path)

        # バックアップファイルが生成されていることを確認
        # backup_count が 5 なので、.1 から .5 までのファイルが作成されるはず
        for g in range(1, 6):
            backup_path = f"{log_file_path}.{g}"
            assert os.path.exists(backup_path), (
                f"Backup file {backup_path} should exist"
            )

        # 6世代目のファイルが存在しないことを確認 (5世代までの管理)
        no_backup_path = f"{log_file_path}.6"
        assert not os.path.exists(no_backup_path), (
            f"Backup file {no_backup_path} should not exist"
        )
