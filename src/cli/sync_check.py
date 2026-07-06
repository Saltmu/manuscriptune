import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

from src.utils import project_config
from src.utils.logger import get_logger

logger = get_logger("sync_check")


def main():
    # Adjust paths if running from src/
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(root_dir, "antigravity.yaml")

    config = project_config.load_project_config(config_path)
    folder_id, creds_path_rel = project_config.get_gdrive_config(config)

    if not folder_id or not creds_path_rel:
        logger.error("Could not find Google Drive configuration in antigravity.yaml")
        return

    # Handle relative paths in config
    if creds_path_rel.startswith("./"):
        creds_path = os.path.join(root_dir, creds_path_rel[2:])
    else:
        creds_path = os.path.join(root_dir, creds_path_rel)

    logger.info("--- Diagnostic Report ---")

    # Check credentials file
    if not os.path.exists(creds_path):
        logger.error(f"Credentials file not found at {creds_path}")
        return
    logger.info("Credentials file found.")

    try:
        # Load credentials
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        service = build("drive", "v3", credentials=creds)

        # Try to list files in the folder
        logger.info(f"Attempting to access folder ID: {folder_id}")
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name)",
            )
            .execute()
        )

        items = results.get("files", [])
        if not items:
            logger.warning("No files found in the folder.")
        else:
            logger.info(f"Found {len(items)} files in folder:")
            for item in items:
                logger.info(f" - {item['name']} ({item['id']})")

    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
