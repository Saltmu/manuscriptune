import logging
import os
from logging.handlers import RotatingFileHandler

from src.utils.project_config import load_project_config
from src.utils.project_paths import PROJECT_ROOT

_initialized = False


def setup_logger() -> None:
    """Sets up the root logger with both StreamHandler and RotatingFileHandler.

    Configuration is loaded from 'antigravity.yaml'.
    """
    global _initialized
    if _initialized:
        return

    # 設定ファイルをロード
    config = load_project_config()
    log_config = config.logging

    # ログレベルの設定 (デフォルトは INFO)
    log_level_str = log_config.level.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # ログ出力先ディレクトリ
    log_dir_name = log_config.dir
    if os.path.isabs(log_dir_name):
        log_dir = log_dir_name
    else:
        log_dir = os.path.join(PROJECT_ROOT, log_dir_name)

    os.makedirs(log_dir, exist_ok=True)

    # ログファイル名
    log_filename = log_config.filename
    log_file_path = os.path.join(log_dir, log_filename)

    # ローテーション設定
    max_bytes = log_config.max_bytes
    backup_count = log_config.backup_count

    # ログフォーマット
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    # ルートロガーの取得
    root_logger = logging.getLogger()
    # ルートロガーの最小レベルを DEBUG に設定し、各ハンドラで実際の出力を制御
    root_logger.setLevel(logging.DEBUG)

    # 既存のハンドラをクリア (重複出力を防止)
    root_logger.handlers.clear()

    # コンソール出力ハンドラ (StreamHandler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ファイル出力ハンドラ (RotatingFileHandler)
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    # ファイルログにはより詳細なデバッグ情報を残すため DEBUG を設定
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Returns a logger with the given name, initializing the logging system if

    not already done.
    """
    setup_logger()
    return logging.getLogger(name)
