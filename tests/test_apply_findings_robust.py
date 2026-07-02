from unittest.mock import patch

import yaml

from src.apply_findings import (
    main,
)


def test_main_sequential_llm_fallback(tmp_path):
    """
    一括LLM適用が失敗（Noneを返す）した際に、自動で個別LLM適用にフォールバックし、
    個別適用が成功することを確認するテスト。
    """
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

    def mock_query_single(context_lines, finding, model):
        fid = finding.get("id")
        context_text = "".join(context_lines)
        if fid == "INT-001":
            return context_text.replace("重天の調べ", "重天の調律")
        elif fid == "INT-002":
            return context_text.replace("悲しげな顔", "憂いを帯びた表情")
        return None

    with (
        patch(
            "src.findings.applier.query_llm_for_block_replacement", return_value=None
        ) as mock_block,
        patch(
            "src.findings.applier.query_llm_for_single_replacement",
            side_effect=mock_query_single,
        ) as mock_single,
    ):
        test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto"]
        with patch("sys.argv", test_args):
            main()

        # 一括適用が呼ばれたことを検証
        mock_block.assert_called_once()
        # 個別適用が呼ばれたことを検証
        assert mock_single.call_count >= 2

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt
    assert "少年は憂いを帯びた表情をして佇んでいた。" in updated_txt

    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert "LLM個別方式" in findings_result["INT-001"]["apply_result"]
    assert findings_result["INT-002"]["apply_status"] == "success"
    assert "LLM個別方式" in findings_result["INT-002"]["apply_result"]


def test_cascade_dynamic_mapping_on_line_shift(tmp_path):
    """
    先行する指摘の適用によって行数がシフト（増加）した場合でも、
    後続の指摘が find_target_line の動的再検索によって正しく適用されることを検証する。
    """
    formatted_txt_content = (
        "L1: 最初の行です。\n" "L2: 二行目です。\n" "L3: 三行目です。\n"
    )
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "最初の行です。",
                "suggestion": "「最初の行です。\n改行が挟まりました。」に修正。",
                "accepted": "y",
            },
            {
                "id": "INT-002",
                "location": "3行目",
                "original": "三行目です。",
                "suggestion": "「三行目（修正済み）です。」に修正。",
                "accepted": "y",
            },
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    # LLMなし (no-llm) でルールベース置換を行う
    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]
    with patch("sys.argv", test_args):
        main()

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    # 元の L1 が 2行に増え、元の L3 (最初は3行目だったが4行目にシフトする) が正しく置換されているか
    assert "最初の行です。\n改行が挟まりました。" in updated_txt
    assert "三行目（修正済み）です。" in updated_txt

    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert findings_result["INT-002"]["apply_status"] == "success"


def test_fuzzy_fallback_matching(tmp_path):
    """
    original に微妙なスペースの揺れがある場合でも、
    高度なルールベース・フォールバックが機能して正しく適用されることを検証する。
    """
    formatted_txt_content = "  少年は　古い楽器を　奏でた。\n"
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "少年は古い楽器を奏でた。",  # スペースがない
                "suggestion": "「少年は古びた弦楽器を奏でた。」に修正。",
                "accepted": "y",
            }
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    # LLMなし (no-llm) でルールベース置換を行う
    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]
    with patch("sys.argv", test_args):
        main()

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "少年は古びた弦楽器を奏でた。" in updated_txt

    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert "フォールバック" in findings_result["INT-001"]["apply_result"]


def test_apply_findings_failure_aborts_without_saving(tmp_path):
    """
    1件でも適用に失敗（failed_count > 0）した場合に、
    小説ファイルやYAMLファイルが上書き保存されず、処理が異常終了することを確認するテスト。
    """
    import pytest

    formatted_txt_content = "少年は佇んでいた。\n"
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "少年は佇んでいた。",
                "suggestion": "「少女は佇んでいた。」に修正。",
                "accepted": "y",
            }
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]
    with (
        patch("sys.argv", test_args),
        patch(
            "src.apply_findings._apply_grouped_findings", return_value=(0, 1)
        ) as mock_apply,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        mock_apply.assert_called_once()

    # 小説本文が元のままであることを確認
    assert formatted_txt_path.read_text(encoding="utf-8") == formatted_txt_content

    # 指記YAMLも変更されていない（acceptedなどが反映されていない）ことを確認
    with open(findings_yaml_path, encoding="utf-8") as f:
        raw_yaml = yaml.safe_load(f)
    assert raw_yaml["findings"][0].get("apply_status") is None


def test_apply_findings_save_exception_rolls_back(tmp_path):
    """
    保存処理の実行中に例外が発生した場合、
    バックアップ（.bak）から元のファイル群が正常に復元されることを検証するテスト。
    """
    import pytest

    formatted_txt_content = "少年は佇んでいた。\n"
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "少年は佇んでいた。",
                "suggestion": "「少女は佇んでいた。」に修正。",
                "accepted": "y",
            }
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]

    # write_file の呼び出し時に意図的に例外を発生させる
    with patch("src.findings.applier.write_file", side_effect=OSError("Disk Full")):
        with patch("sys.argv", test_args):
            with pytest.raises(IOError) as exc_info:
                main()
            assert "Disk Full" in str(exc_info.value)

    # ロールバックされ、小説本文とYAMLが元の状態を維持していることを検証
    assert formatted_txt_path.read_text(encoding="utf-8") == formatted_txt_content
    with open(findings_yaml_path, encoding="utf-8") as f:
        raw_yaml = yaml.safe_load(f)
    assert raw_yaml["findings"][0].get("apply_status") is None
    # バックアップファイル（.bak）がクリーンアップされていることを検証
    assert not (tmp_path / "01_formatted.txt.bak").exists()
    assert not (tmp_path / "00_integrated_findings.yaml.bak").exists()
