import os
from unittest.mock import mock_open, patch

from src.utils.project_config import (
    get_gdrive_config,
    get_novel_setting,
    load_project_config,
    natural_sort_key,
    resolve_latest_file,
    resolve_novel_file_by_pattern,
)


def test_natural_sort_key():
    assert natural_sort_key("episode10") == ["episode", 10, ""]
    assert natural_sort_key("10episode") == ["", 10, "episode"]
    assert natural_sort_key("ep2") < natural_sort_key("ep10")
    assert natural_sort_key("EP2") == natural_sort_key("ep2")


def test_load_project_config_not_exist():
    with patch("os.path.exists", return_value=False):
        assert load_project_config() == {}


def test_load_project_config_valid():
    yaml_content = """
project:
  novel:
    title: "重天の調律師"
    author: "調律師"
"""
    with (
        patch("os.path.exists", return_value=True),
        patch("builtins.open", mock_open(read_data=yaml_content)),
    ):
        config = load_project_config()
        assert config["project"]["novel"]["title"] == "重天の調律師"


def test_load_project_config_invalid():
    yaml_content = """
project:
  novel:
    title: "重天の調律師"
  - invalid_yaml_syntax
"""
    with (
        patch("os.path.exists", return_value=True),
        patch("builtins.open", mock_open(read_data=yaml_content)),
    ):
        assert load_project_config() == {}


def test_get_novel_setting():
    mock_config = {
        "project": {
            "novel": {
                "title": "重天の調律師",
                "file_patterns": {"plot": "data/sources/plot_*.txt"},
            }
        }
    }
    with patch(
        "src.utils.project_config.load_project_config", return_value=mock_config
    ):
        assert get_novel_setting("title") == "重天の調律師"
        assert get_novel_setting("non_existent", "default_val") == "default_val"


def test_resolve_latest_file(tmp_path):
    file1 = tmp_path / "plot_1.txt"
    file2 = tmp_path / "plot_10.txt"
    file3 = tmp_path / "plot_2.txt"

    file1.touch()
    file2.touch()
    file3.touch()

    pattern = str(tmp_path / "plot_*.txt")
    latest = resolve_latest_file(pattern)
    assert os.path.basename(latest) == "plot_10.txt"


def test_resolve_latest_file_no_match():
    assert (
        resolve_latest_file("non_existent_pattern*", "fallback.txt") == "fallback.txt"
    )


def test_resolve_novel_file_by_pattern(tmp_path):
    mock_config = {"project": {"novel": {"file_patterns": {"plot": "plot_*.txt"}}}}

    with (
        patch("src.utils.project_config.load_project_config", return_value=mock_config),
        patch("src.utils.project_config.resolve_latest_file") as mock_resolve,
    ):
        expected_return = os.path.join("data", "sources", "plot_2.txt")
        mock_resolve.return_value = expected_return
        res = resolve_novel_file_by_pattern("plot", "plot_default.txt")
        expected_pattern = os.path.join("data", "sources", "plot_*.txt")
        mock_resolve.assert_called_once_with(expected_pattern, None)
        assert res == expected_return


def test_get_gdrive_config_toplevel():
    """google_drive: トップレベルキーから設定を取得できる"""
    config = {
        "google_drive": {
            "type": "google-drive",
            "folder_id": "test_folder_id",
            "auth_file": "./credentials/test.json",
        }
    }
    folder_id, auth_file = get_gdrive_config(config)
    assert folder_id == "test_folder_id"
    assert auth_file == "./credentials/test.json"


def test_get_gdrive_config_legacy_skills_sources():
    """後方互換：skills[].sources[] から設定を取得できる"""
    config = {
        "skills": [
            {
                "path": "./skills/consistency-checker",
                "sources": [
                    {
                        "type": "google-drive",
                        "folder_id": "legacy_folder_id",
                        "auth_file": "./credentials/legacy.json",
                    }
                ],
            }
        ]
    }
    folder_id, auth_file = get_gdrive_config(config)
    assert folder_id == "legacy_folder_id"
    assert auth_file == "./credentials/legacy.json"


def test_get_gdrive_config_not_found():
    """Google Drive 設定が存在しない場合は (None, None) を返す"""
    config = {"skills": [{"path": "./skills/novel-formatter"}]}
    folder_id, auth_file = get_gdrive_config(config)
    assert folder_id is None
    assert auth_file is None


def test_get_gdrive_config_empty():
    """設定が空の場合は (None, None) を返す"""
    folder_id, auth_file = get_gdrive_config({})
    assert folder_id is None
    assert auth_file is None
