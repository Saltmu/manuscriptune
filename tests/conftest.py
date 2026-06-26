import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_ai_client():
    client = MagicMock()
    client.generate.return_value = "Mocked Response"
    return client


@pytest.fixture
def dummy_project_dir(tmp_path):
    """Creates a temporary project directory layout with a dummy antigravity.yaml."""
    # Create structure
    os.makedirs(tmp_path / "novels", exist_ok=True)
    os.makedirs(tmp_path / "data" / "sources", exist_ok=True)
    os.makedirs(tmp_path / "skills" / "logic-consistency-reviewer", exist_ok=True)
    os.makedirs(tmp_path / "skills" / "style-expression-reviewer", exist_ok=True)
    os.makedirs(tmp_path / "skills" / "novel-formatter", exist_ok=True)

    # Write dummy SKILL.md files
    (tmp_path / "skills" / "logic-consistency-reviewer" / "SKILL.md").write_text(
        "logic-consistency-reviewer skill prompt", encoding="utf-8"
    )
    (tmp_path / "skills" / "style-expression-reviewer" / "SKILL.md").write_text(
        "style-expression-reviewer skill prompt", encoding="utf-8"
    )
    (tmp_path / "skills" / "novel-formatter" / "SKILL.md").write_text(
        "novel-formatter skill prompt", encoding="utf-8"
    )

    # Write dummy antigravity.yaml
    yaml_content = """
project:
  novel:
    title: "テスト小説"
    author: "テスト著者"
    file_patterns:
      settings: "*設定資料集*.txt"
      character: "*キャラクター概要*.txt"
      plot: "*プロット*.txt"

skills:
  - name: "Google Drive Sync"
    sources:
      - type: "google-drive"
        folder_id: "dummy_folder_id"
        auth_file: "./credentials/service_account.json"
"""
    (tmp_path / "antigravity.yaml").write_text(yaml_content, encoding="utf-8")

    # Create dummy credentials file
    os.makedirs(tmp_path / "credentials", exist_ok=True)
    (tmp_path / "credentials" / "service_account.json").write_text(
        '{"type": "service_account"}', encoding="utf-8"
    )

    return tmp_path
