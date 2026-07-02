import glob
import os
import re

from src.utils.yaml_handler import YamlHandler


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


def load_project_config(config_path: str | None = None, validate: bool = True):
    if config_path:
        cfg = YamlHandler.load_safe(config_path)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        config_path = os.path.join(project_root, "antigravity.yaml")
        if not os.path.exists(config_path):
            config_path = "antigravity.yaml"
        cfg = YamlHandler.load_safe(config_path)

    if validate and cfg:
        validate_project_skills(cfg)
    return cfg


def validate_project_skills(config: dict) -> None:
    """Validates the skills registered in the project config."""
    from src.utils.skill_registry import SkillRegistry, SkillValidationError

    skills_config = config.get("skills", [])
    if not skills_config:
        return

    registry = SkillRegistry()
    loaded_skills = {}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))

    for skill_item in skills_config:
        path = skill_item.get("path")
        if not path:
            raise SkillValidationError("Skill path configuration is missing.")

        # Resolve path relative to project root if relative
        if not os.path.isabs(path):
            full_path = os.path.join(project_root, path)
        else:
            full_path = path

        skill_md_path = os.path.join(full_path, "SKILL.md")
        if not os.path.exists(skill_md_path):
            raise SkillValidationError(
                f"SKILL.md not found at '{skill_md_path}' for skill path '{path}'."
            )

        skill = registry.load_skill_from_file(skill_md_path)
        loaded_skills[skill.name] = skill

    registry.check_dependencies(loaded_skills)


def get_gdrive_config(config: dict | None = None) -> tuple[str | None, str | None]:
    """Extracts folder_id and auth_file for Google Drive source from config.

    Looks for configuration in the following order:
    1. Top-level ``google_drive:`` key (preferred)
    2. ``skills[].sources[]`` with ``type: google-drive`` (legacy)
    """
    cfg = config if config is not None else load_project_config()
    if not cfg:
        return None, None

    # 1. トップレベルの google_drive: セクションを優先参照
    gdrive = cfg.get("google_drive")
    if gdrive and gdrive.get("type") == "google-drive":
        return gdrive.get("folder_id"), gdrive.get("auth_file")

    # 2. 後方互換：skills[].sources[] から検索
    for skill in cfg.get("skills", []):
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
    from src.utils.project_paths import DATA_DIR, DATA_SOURCES_DIR, SOURCES_DIR

    file_patterns = get_novel_setting("file_patterns", {})
    pattern = file_patterns.get(pattern_key, default_pattern)
    if not pattern.startswith(f"{DATA_SOURCES_DIR}/"):
        pattern = os.path.join(DATA_DIR, SOURCES_DIR, pattern)
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
