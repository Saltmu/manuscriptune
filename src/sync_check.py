import os

import yaml
from google.oauth2 import service_account
from googleapiclient.discovery import build


def load_config(config_path="antigravity.yaml"):
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
    # Adjust paths if running from src/
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(root_dir, "antigravity.yaml")

    config = load_config(config_path)
    folder_id, creds_path_rel = get_gdrive_config(config)

    if not folder_id or not creds_path_rel:
        print("[ERROR] Could not find Google Drive configuration in antigravity.yaml")
        return

    # Handle relative paths in config
    if creds_path_rel.startswith("./"):
        creds_path = os.path.join(root_dir, creds_path_rel[2:])
    else:
        creds_path = os.path.join(root_dir, creds_path_rel)

    print("--- Diagnostic Report ---")

    # Check credentials file
    if not os.path.exists(creds_path):
        print(f"[ERROR] Credentials file not found at {creds_path}")
        return
    print("[OK] Credentials file found.")

    try:
        # Load credentials
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        service = build("drive", "v3", credentials=creds)

        # Try to list files in the folder
        print(f"[INFO] Attempting to access folder ID: {folder_id}")
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
            print("[WARNING] No files found in the folder.")
        else:
            print(f"[OK] Found {len(items)} files in folder:")
            for item in items:
                print(f" - {item['name']} ({item['id']})")

    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")


if __name__ == "__main__":
    main()
