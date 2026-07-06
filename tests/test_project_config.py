from src.utils import project_paths
from src.utils.project_config import AppConfig, load_project_config


def test_load_project_config_schema(tmp_path):
    yaml_content = """
version: "1.0"
project:
  name: "test-project"
  novel:
    main_characters:
      - "アルフ"
      - "ミーナ"
    novels_dir: "custom_novels"
    results_dir: "custom_reviews"
agent:
  name: "Editor-AI"
  model: "gemini-3.5-flash"
google_drive:
  type: "google-drive"
  folder_id: "folder_123"
  auth_file: "./credentials/key.json"
skills:
  - path: "./skills/novel-formatter"
logging:
  level: "INFO"
"""
    config_file = tmp_path / "antigravity.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    # load_project_config で AppConfig インスタンスが正しくロードされるか
    cfg = load_project_config(str(config_file), validate=False)
    assert isinstance(cfg, AppConfig)
    assert cfg.project.name == "test-project"
    assert cfg.project.novel.novels_dir == "custom_novels"
    assert cfg.google_drive.folder_id == "folder_123"


def test_project_paths_dynamic_resolution(tmp_path):
    yaml_content = """
version: "1.0"
project:
  name: "test-project"
  novel:
    novels_dir: "custom_novels"
    data_dir: "custom_data"
    sources_dir: "custom_sources"
    results_dir: "custom_reviews"
agent:
  name: "Editor"
skills: []
"""
    config_file = tmp_path / "antigravity.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")

    # 設定ファイルをロード
    load_project_config(str(config_file), validate=False)

    # project_paths 内の解決関数がカスタムパスを返すか確認
    novels_dir = project_paths.get_novels_dir()
    assert "custom_novels" in novels_dir

    sources_dir = project_paths.get_sources_dir()
    assert "custom_data/custom_sources" in sources_dir.replace("\\", "/")
