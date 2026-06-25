from unittest.mock import patch

import yaml

from src.apply_findings import (
    apply_finding_to_text,
    extract_suggestion_candidate,
    main,
    parse_line_number,
)


def test_parse_line_number():
    assert parse_line_number("8行目") == 8
    assert parse_line_number("15") == 15
    assert parse_line_number(None) is None
    assert parse_line_number("行数不明") is None
    assert parse_line_number("第123行目") == 123


def test_extract_suggestion_candidate():
    assert (
        extract_suggestion_candidate("「こんにちは」に修正してください。")
        == "こんにちは"
    )
    assert (
        extract_suggestion_candidate("「二つの色」または「エネルギー」に変更。")
        == "エネルギー"
    )
    assert extract_suggestion_candidate("単なる説明文のみ") is None


def test_apply_finding_to_text_success_extracted():
    # Test case where LLM is disabled, and it extracts the replacement from the suggestion
    text_lines = [
        "昔々、あるところにおじいさんとおばあさんが住んでいました。\n",
        "おじいさんは山へしば刈りに行きました。\n",
        "おばあさんは川へ洗濯に行きました。\n",
    ]
    finding = {
        "id": "INT-001",
        "location": "2行目",
        "original": "しば刈り",
        "suggestion": "「芝刈り」に修正してください。",
    }

    # use_llm=False
    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is True
    assert applied_text == "芝刈り"
    assert method == "extracted"
    assert text_lines[1] == "おじいさんは山へ芝刈りに行きました。\n"


def test_apply_finding_to_text_not_found():
    text_lines = [
        "おじいさんは山へしば刈りに行きました。\n",
    ]
    finding = {
        "id": "INT-002",
        "location": "1",
        "original": "川へ洗濯",
        "suggestion": "「海へ釣り」に修正",
    }

    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is False
    assert "Could not find original text" in applied_text
    assert method is None


def test_apply_finding_to_text_no_candidate():
    text_lines = [
        "おじいさんは山へしば刈りに行きました。\n",
    ]
    finding = {
        "id": "INT-003",
        "location": "1",
        "original": "しば刈り",
        "suggestion": "漢字表記を修正してください。",  # No quotes
    }

    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is False
    assert "Could not extract replacement text" in applied_text
    assert method is None


def test_main_block_merging_auto_fallback(tmp_path):
    # テスト用のテキストファイル作成
    formatted_txt_content = (
        "第１章　重天の調べ\n"
        "少年は悲しげな顔をして佇んでいた。\n"
        "その手には古い楽器が握られている。\n"
    )
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    # テスト用の指摘YAML作成
    # 隣接行に2つの指摘を配置して、同じブロックとしてマージされるかを検証
    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "重天の調べ",
                "suggestion": "「重天の調律」に修正してください。",
                "accepted": "y",
            },
            {
                "id": "INT-002",
                "location": "2行目",
                "original": "悲しげな顔",
                "suggestion": "「憂いを帯びた表情」に修正してください。",
                "accepted": "y",
            },
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    # コマンドライン引数をシミュレートして main を呼び出す
    # --auto --no-llm を指定して、LLMなしで自動適用
    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]
    with patch("sys.argv", test_args):
        main()

    # 小説テキストが正しく更新されたか検証
    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt
    assert "少年は憂いを帯びた表情をして佇んでいた。" in updated_txt

    # 指摘YAMLが正しく更新されたか検証
    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert "extracted" in findings_result["INT-001"]["apply_result"]
    assert findings_result["INT-002"]["apply_status"] == "success"
    assert "extracted" in findings_result["INT-002"]["apply_result"]


def test_main_block_merging_auto_llm(tmp_path):
    formatted_txt_content = (
        "第１章　重天の調べ\n"
        "少年は悲しげな顔をして佇んでいた。\n"
        "その手には古い楽器が握られている。\n"
    )
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "重天の調べ",
                "suggestion": "「重天の調律」に修正してください。",
                "accepted": "y",
            },
            {
                "id": "INT-002",
                "location": "2行目",
                "original": "悲しげな顔",
                "suggestion": "「憂いを帯びた表情」に修正してください。",
                "accepted": "y",
            },
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    # LLMのレスポンスをモック
    # コンテキスト全体を書き換えた結果を返す
    llm_output = (
        "第１章　重天の調律\n"
        "少年は憂いを帯びた表情をして佇んでいた。\n"
        "その手には古い楽器が握られている。\n"
    )

    with patch(
        "src.apply_findings.query_llm_for_block_replacement", return_value=llm_output
    ) as mock_llm:
        test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto"]
        with patch("sys.argv", test_args):
            main()

        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        assert len(args[0]) == 3
        assert len(args[1]) == 2
        assert args[1][0]["id"] == "INT-001"
        assert args[1][1]["id"] == "INT-002"

    # 小説テキストが正しく更新されたか検証
    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt
    assert "少年は憂いを帯びた表情をして佇んでいた。" in updated_txt

    # 指摘YAMLが正しく更新されたか検証
    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert "LLM" in findings_result["INT-001"]["apply_result"]
    assert findings_result["INT-002"]["apply_status"] == "success"
    assert "LLM" in findings_result["INT-002"]["apply_result"]
