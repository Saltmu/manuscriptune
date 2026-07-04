import io
import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.utils import project_config, project_paths
from src.utils.logger import get_logger

logger = get_logger("sync_gdrive")


def _check_lock_and_cache(cache_file: str, lock_file: str, cache_duration: int) -> bool:
    """
    Checks if another sync process is running or if the cache is still fresh.
    Returns True if we should proceed with sync, False otherwise.
    """
    if os.path.exists(lock_file):
        logger.warning("Another sync process is running. Waiting or skipping...")
        return False

    if os.path.exists(cache_file):
        last_sync = os.path.getmtime(cache_file)
        if time.time() - last_sync < cache_duration:
            logger.info("Recently synced. Skipping...")
            return False

    return True


def _download_gdrive_file(service, item, output_dir: str) -> None:
    """
    Downloads a single file from Google Drive, exporting Google Docs as text.
    """
    name = item["name"]
    file_id = item["id"]
    mime_type = item["mimeType"]

    logger.info(f"Processing: {name} ({mime_type})")

    if mime_type == "application/vnd.google-apps.folder":
        logger.info(f"Skipping folder: {name}")
        return
    elif mime_type == "application/vnd.google-apps.document":
        request = service.files().export_media(fileId=file_id, mimeType="text/plain")
        file_path = os.path.join(output_dir, f"{name}.txt")
    elif mime_type.startswith("application/vnd.google-apps."):
        logger.warning(
            f"Skipping unsupported Google Workspace file: {name} ({mime_type})"
        )
        return
    else:
        request = service.files().get_media(fileId=file_id)
        file_path = os.path.join(output_dir, name)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()

    with open(file_path, "wb") as f:
        f.write(fh.getvalue())
    logger.info(f"Saved to {file_path}")


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(root_dir, "antigravity.yaml")

    CACHE_FILE = os.path.join(root_dir, ".sync_cache")
    LOCK_FILE = os.path.join(root_dir, ".sync.lock")
    CACHE_DURATION = 1800  # 30 minutes in seconds

    if not _check_lock_and_cache(CACHE_FILE, LOCK_FILE, CACHE_DURATION):
        return

    config = project_config.load_project_config(config_path)
    folder_id, creds_path_rel = project_config.get_gdrive_config(config)

    if not folder_id or not creds_path_rel:
        logger.error("Could not find Google Drive configuration in antigravity.yaml")
        return

    creds_path = (
        os.path.join(root_dir, creds_path_rel[2:])
        if creds_path_rel.startswith("./")
        else os.path.join(root_dir, creds_path_rel)
    )

    output_dir = os.path.join(root_dir, project_paths.DATA_SOURCES_DIR)

    try:
        # Create lock
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        service = build("drive", "v3", credentials=creds)

        logger.info(f"Downloading files from folder: {folder_id}...")
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id, name, mimeType)",
            )
            .execute()
        )

        items = results.get("files", [])
        for item in items:
            _download_gdrive_file(service, item, output_dir)

        # Update cache timestamp
        with open(CACHE_FILE, "w") as f:
            f.write(str(time.time()))

        # Remove sync_status.yaml on success
        status_path = os.path.join(output_dir, "sync_status.yaml")
        if os.path.exists(status_path):
            try:
                os.remove(status_path)
                logger.info(f"Removed sync status file: {status_path}")
            except Exception as e:
                logger.warning(f"Failed to remove sync status file: {e}")

    except Exception as e:
        logger.error(f"Google Drive sync failed: {e}", exc_info=True)
        # Write failure status to sync_status.yaml
        status_path = os.path.join(output_dir, "sync_status.yaml")
        try:
            from src.utils.yaml_handler import YamlHandler

            YamlHandler.dump(
                {
                    "_metadata": {
                        "fallback_mode": True,
                        "reason": f"Google Drive sync failed: {str(e)}",
                        "completeness": "low",
                    }
                },
                status_path,
            )
            logger.info(f"Saved failed sync status to {status_path}")
        except Exception as ex:
            logger.error(f"Failed to write sync_status.yaml: {ex}")
        raise e
    finally:
        # Remove lock
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)


if __name__ == "__main__":
    main()
