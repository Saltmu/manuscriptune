import io
import os
import time

import yaml
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def load_config(config_path):
    if not os.path.exists(config_path):
        return None
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_gdrive_config(config):
    if not config or "skills" not in config:
        return None, None
    for skill in config["skills"]:
        if "sources" in skill:
            for source in skill["sources"]:
                if source.get("type") == "google-drive":
                    return source.get("folder_id"), source.get("auth_file")
    return None, None


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(root_dir, "antigravity.yaml")

    CACHE_FILE = os.path.join(root_dir, ".sync_cache")
    LOCK_FILE = os.path.join(root_dir, ".sync.lock")
    CACHE_DURATION = 3000  # 30 minutes in seconds

    # Check if another process is already syncing
    if os.path.exists(LOCK_FILE):
        print("Another sync process is running. Waiting or skipping...")
        return

    # Check cache
    if os.path.exists(CACHE_FILE):
        last_sync = os.path.getmtime(CACHE_FILE)
        if time.time() - last_sync < CACHE_DURATION:
            print("Recently synced. Skipping...")
            return

    config = load_config(config_path)
    folder_id, creds_path_rel = get_gdrive_config(config)

    if not folder_id or not creds_path_rel:
        print("[ERROR] Could not find Google Drive configuration in antigravity.yaml")
        return

    if creds_path_rel.startswith("./"):
        creds_path = os.path.join(root_dir, creds_path_rel[2:])
    else:
        creds_path = os.path.join(root_dir, creds_path_rel)

    output_dir = os.path.join(root_dir, "data/sources")

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

        print(f"Downloading files from folder: {folder_id}...")
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
            name = item["name"]
            file_id = item["id"]
            mime_type = item["mimeType"]

            print(f"Processing: {name} ({mime_type})")

            if mime_type == "application/vnd.google-apps.folder":
                print(f"Skipping folder: {name}")
                continue
            elif mime_type == "application/vnd.google-apps.document":
                request = service.files().export_media(
                    fileId=file_id, mimeType="text/plain"
                )
                file_path = os.path.join(output_dir, f"{name}.txt")
            elif mime_type.startswith("application/vnd.google-apps."):
                print(
                    f"Skipping unsupported Google Workspace file: {name} ({mime_type})"
                )
                continue
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
            print(f"Saved to {file_path}")

        # Update cache timestamp
        with open(CACHE_FILE, "w") as f:
            f.write(str(time.time()))

    finally:
        # Remove lock
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)


if __name__ == "__main__":
    main()
