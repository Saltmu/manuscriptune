import glob
import os
import re

import yaml


def natural_sort_key(s):
    """
    自然順（Natural Sort）用のソートキー。
    文字列中の数字を数値オブジェクトとして抽出し、正しく比較できるようにします。
    """
    s_str = str(s)
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", s_str)
    ]


def load_project_config(config_path: str | None = None):
    if config_path:
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    config_path = os.path.join(project_root, "antigravity.yaml")
    if not os.path.exists(config_path):
        config_path = "antigravity.yaml"
        if not os.path.exists(config_path):
            return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_gdrive_config(config: dict | None = None) -> tuple[str | None, str | None]:
    """Extracts folder_id and auth_file for Google Drive source from config."""
    cfg = config if config is not None else load_project_config()
    if not cfg or "skills" not in cfg:
        return None, None
    for skill in cfg["skills"]:
        if "sources" in skill:
            for source in skill["sources"]:
                if source.get("type") == "google-drive":
                    return source.get("folder_id"), source.get("auth_file")
    return None, None


def get_novel_setting(key, default=None):
    config = load_project_config()
    novel_config = config.get("project", {}).get("novel", {})
    return novel_config.get(key, default)


def resolve_novel_file_by_pattern(pattern_key, default_pattern, default_fallback=None):
    file_patterns = get_novel_setting("file_patterns", {})
    pattern = file_patterns.get(pattern_key, default_pattern)
    if not pattern.startswith("data/sources/"):
        pattern = os.path.join("data", "sources", pattern)
    return resolve_latest_file(pattern, default_fallback)


def resolve_latest_file(pattern, default=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    full_pattern = os.path.join(project_root, pattern)
    files = glob.glob(full_pattern)
    if not files:
        files = glob.glob(pattern)
        if not files:
            return default
    files.sort(key=natural_sort_key)
    return files[-1]
