from unittest.mock import patch

import pytest

from src.services.chat_service import ChatService, parse_llm_chat_response
from src.utils.yaml_handler import YamlHandler


@pytest.fixture
def temp_findings_yaml(tmp_path):
    # テスト用の YAML ファイルを作成
    yaml_path = tmp_path / "test_findings.yaml"
    initial_data = {
        "findings": [
            {
                "id": "INT-001",
                "accepted": "n",
                "original": "オレの脈動と、コンデンサの音。",
                "suggestion": "「和音」という表現を変更してください。",
                "analysis": "音響的に不自然です。",
            }
        ]
    }
    YamlHandler.dump(initial_data, str(yaml_path))
    return yaml_path


def test_parse_llm_chat_response_with_suggestion():
    # LLMの応答テキストに設定資料修正提案が含まれている場合
    llm_output = """
ユーザーの意図を理解しました。設定資料を変更すべきです。

<source_suggestion>
file: 魔力体系.txt
original: 魔力は中心に収束する
replacement: 魔力は境界線から外側へと発散する
reason: 大調律圏の魔力フロー仕様の変更に伴う整合性維持のため。
</source_suggestion>

修正内容はこれでいかがでしょうか。
"""
    reply, suggestion = parse_llm_chat_response(llm_output)

    assert "ユーザーの意図を理解しました" in reply
    assert "修正内容はこれでいかがでしょうか" in reply
    assert suggestion is not None
    assert suggestion["file"] == "魔力体系.txt"
    assert suggestion["original"] == "魔力は中心に収束する"
    assert suggestion["replacement"] == "魔力は境界線から外側へと発散する"
    assert "大調律圏" in suggestion["reason"]


def test_parse_llm_chat_response_without_suggestion():
    llm_output = "単なる対話応答のみで、設定資料の変更はありません。"
    reply, suggestion = parse_llm_chat_response(llm_output)

    assert reply == llm_output
    assert suggestion is None


@patch("src.services.chat_service.AgyClient.generate")
@patch("src.services.chat_service.novel_service.resolve_paths")
def test_chat_service_chat_flow(mock_resolve_paths, mock_generate, temp_findings_yaml):
    # パス解決のモック
    mock_resolve_paths.return_value = ("/dummy/novel.txt", str(temp_findings_yaml))

    # LLM応答のモック
    mock_generate.return_value = """
わかりました。設定を変更しましょう。

<source_suggestion>
file: 魔力体系.txt
original: 魔力は中心に収束する
replacement: 魔力は境界線から外側へと発散する
reason: 設定変更のため。
</source_suggestion>
"""

    service = ChatService()
    result = service.chat(
        novel_name="test_novel.txt",
        finding_id="INT-001",
        message="魔力は外側に発散する設定にしたいです。",
    )

    assert result["status"] == "success"
    assert "わかりました" in result["reply"]
    assert result["source_suggestion"] is not None
    assert result["source_suggestion"]["file"] == "魔力体系.txt"

    # YAMLに永続化されているか確認
    updated_data = YamlHandler.load(str(temp_findings_yaml))
    findings = updated_data["findings"]
    finding = next(f for f in findings if f["id"] == "INT-001")

    # 会話履歴が追加されていること
    assert "discussion" in finding
    assert len(finding["discussion"]) == 2
    assert finding["discussion"][0]["role"] == "user"
    assert (
        finding["discussion"][0]["content"] == "魔力は外側に発散する設定にしたいです。"
    )
    assert finding["discussion"][1]["role"] == "assistant"
    assert "わかりました" in finding["discussion"][1]["content"]

    # 提案が保存されていること
    assert "source_suggestion" in finding
    assert finding["source_suggestion"]["file"] == "魔力体系.txt"
