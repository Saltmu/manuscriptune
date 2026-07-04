import glob
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from src.utils.yaml_handler import YamlHandler

# --- Pydantic Schema for configuration ---


class ProjectNovelConfig(BaseModel):
    main_characters: list[str] = Field(default_factory=list)
    file_patterns: dict[str, str] = Field(default_factory=dict)
    # Directory paths configurable via YAML
    novels_dir: str = "novels"
    data_dir: str = "data"
    sources_dir: str = "sources"
    results_dir: str = "reviews"


class ProjectConfigSection(BaseModel):
    name: str = "novel-tools-system"
    description: str = ""
    novel: ProjectNovelConfig = Field(default_factory=ProjectNovelConfig)


class AgentConfig(BaseModel):
    name: str = "Editor-AI"
    model: str = "gemini-3.5-flash"
    temperature: float = 0.2
    context_caching: bool = True
    system_prompt: str = ""


class GoogleDriveConfig(BaseModel):
    type: str = "google-drive"
    folder_id: str | None = None
    auth_file: str | None = None


class SkillConfig(BaseModel):
    path: str


class LoggingConfig(BaseModel):
    level: str = "INFO"
    dir: str = "logs"
    filename: str = "app.log"
    max_bytes: int = 10485760
    backup_count: int = 5


class AppConfig(BaseModel):
    version: str = "1.0"
    project: ProjectConfigSection = Field(default_factory=ProjectConfigSection)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    google_drive: GoogleDriveConfig | None = None
    skills: list[SkillConfig] = Field(default_factory=list)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# --- Configuration Manager ---

_config_cache: AppConfig | None = None
_last_config_path: str | None = None


def clear_config_cache() -> None:
    """Clears the configuration cache, forcing a reload on the next call."""
    global _config_cache, _last_config_path
    _config_cache = None
    _last_config_path = None


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


def load_project_config(
    config_path: str | None = None, validate: bool = True, force_reload: bool = False
) -> AppConfig:
    global _config_cache, _last_config_path

    if (
        not force_reload
        and _config_cache is not None
        and (config_path is None or config_path == _last_config_path)
    ):
        return _config_cache

    raw_cfg = None
    if config_path:
        raw_cfg = YamlHandler.load_safe(config_path)
        _last_config_path = config_path
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        config_path = os.path.join(project_root, "antigravity.yaml")
        if os.path.exists(config_path):
            raw_cfg = YamlHandler.load_safe(config_path)
            _last_config_path = config_path
        else:
            config_path = "antigravity.yaml"
            if os.path.exists(config_path):
                raw_cfg = YamlHandler.load_safe(config_path)
                _last_config_path = config_path

    if not raw_cfg:
        # Fallback to default config if yaml cannot be loaded
        cfg = AppConfig()
    else:
        # Parse and validate with Pydantic
        cfg = AppConfig.model_validate(raw_cfg)

    if validate and raw_cfg:
        validate_project_skills(cfg)

    _config_cache = cfg

    # Update project_paths constants to maintain backward compatibility
    from src.utils import project_paths

    project_paths.update_constants(
        novels=cfg.project.novel.novels_dir,
        data=cfg.project.novel.data_dir,
        sources=cfg.project.novel.sources_dir,
        results=cfg.project.novel.results_dir,
    )

    return cfg


def validate_project_skills(config: AppConfig) -> None:
    """Validates the skills registered in the project config."""
    from src.utils.skill_registry import SkillRegistry, SkillValidationError

    skills_config = config.skills
    if not skills_config:
        return

    registry = SkillRegistry()
    loaded_skills = {}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))

    for skill_item in skills_config:
        path = skill_item.path
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


def get_gdrive_config(config: AppConfig | None = None) -> tuple[str | None, str | None]:
    """Extracts folder_id and auth_file for Google Drive source from config."""
    cfg = config if config is not None else load_project_config()
    if not cfg or not cfg.google_drive:
        return None, None

    return cfg.google_drive.folder_id, cfg.google_drive.auth_file


def get_novel_setting(key: str, default: Any = None) -> Any:
    config = load_project_config()
    novel_dict = config.project.novel.model_dump()
    return novel_dict.get(key, default)


def resolve_novel_file_by_pattern(
    pattern_key: str, default_pattern: str, default_fallback: Any = None
) -> Any:
    # Avoid circular import by using dynamic import inside functions
    from src.utils.project_paths import get_sources_dir

    file_patterns = get_novel_setting("file_patterns", {})
    pattern = file_patterns.get(pattern_key, default_pattern)

    # Resolve relative to sources directory dynamically
    sources_dir = get_sources_dir()
    if not os.path.isabs(pattern):
        # Check if the pattern already references the data/sources path, if so extract basename
        if "data/sources" in pattern or "data\\sources" in pattern:
            pattern = os.path.basename(pattern)
        full_pattern = os.path.join(sources_dir, pattern)
    else:
        full_pattern = pattern

    return resolve_latest_file(full_pattern, default_fallback)


def resolve_latest_file(pattern: str, default: Any = None) -> Any:
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
