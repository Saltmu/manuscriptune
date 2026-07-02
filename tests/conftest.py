import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_ai_client():
    client = MagicMock()
    client.generate.return_value = "Mocked Response"
    return client


@pytest.fixture
def mock_gdrive_service():
    """Google Drive API サービスオブジェクトのモック"""
    service = MagicMock()

    # files() リソースのモック
    files_mock = MagicMock()
    service.files.return_value = files_mock

    # list() メソッドのモック
    list_mock = MagicMock()
    files_mock.list.return_value = list_mock
    list_mock.execute.return_value = {"files": []}

    # export_media() メソッドのモック
    export_mock = MagicMock()
    files_mock.export_media.return_value = export_mock

    # get_media() メソッドのモック
    get_media_mock = MagicMock()
    files_mock.get_media.return_value = get_media_mock

    return service


@pytest.fixture
def mock_gdrive_build(mock_gdrive_service):
    """googleapiclient.discovery.build をモックして、mock_gdrive_service を返すようにするフィクスチャ"""
    with patch(
        "googleapiclient.discovery.build", return_value=mock_gdrive_service
    ) as mock_build:
        yield mock_build


@pytest.fixture
def mock_agy_client():
    """AgyClient の generate メソッドと list_models クラスメソッドをモック化するフィクスチャ"""
    with (
        patch("src.utils.ai_client.AgyClient.generate") as mock_gen,
        patch("src.utils.ai_client.AgyClient.list_models") as mock_list_models,
    ):
        mock_gen.return_value = "Mocked Response"
        mock_list_models.return_value = ["Mocked Model"]
        yield {"generate": mock_gen, "list_models": mock_list_models}


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
