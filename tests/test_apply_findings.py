import builtins
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.apply_findings import main
from src.findings.applier import (
    _determine_accepted_findings,
    _interactive_choice,
    _save_outputs_and_print_summary,
)
from src.findings.replacer import (
    extract_suggestion_candidate,
    query_llm_for_block_replacement,
)
from src.findings.text_matcher import find_target_line, parse_line_number


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


def test_main_block_merging_auto_fallback(tmp_path):
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

    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto", "--no-llm"]
    with patch("sys.argv", test_args):
        main()

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt
    assert "少年は憂いを帯びた表情をして佇んでいた。" in updated_txt

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

    llm_output = (
        "第１章　重天の調律\n"
        "少年は憂いを帯びた表情をして佇んでいた。\n"
        "その手には古い楽器が握られている。\n"
    )

    with patch(
        "src.findings.applier.query_llm_for_block_replacement", return_value=llm_output
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

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt
    assert "少年は憂いを帯びた表情をして佇んでいた。" in updated_txt

    with open(findings_yaml_path, encoding="utf-8") as f:
        updated_yaml = yaml.safe_load(f)

    findings_result = {f["id"]: f for f in updated_yaml["findings"]}
    assert findings_result["INT-001"]["apply_status"] == "success"
    assert "LLM" in findings_result["INT-001"]["apply_result"]
    assert findings_result["INT-002"]["apply_status"] == "success"
    assert "LLM" in findings_result["INT-002"]["apply_result"]


def test_main_prevents_writing_to_sources(tmp_path):
    sources_dir = tmp_path / "data" / "sources" / "volume1"
    sources_dir.mkdir(parents=True, exist_ok=True)

    formatted_txt_path = sources_dir / "volume1_formatted.txt"
    formatted_txt_path.write_text("本文", encoding="utf-8")

    findings_yaml_path = sources_dir / "volume1_findings.yaml"
    findings_yaml_path.write_text("findings: []", encoding="utf-8")

    test_args = ["apply_findings.py", "--dir", str(sources_dir), "--auto"]
    with patch("sys.argv", test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1


# --- 新規テスト: 各種分岐の網羅 ---


def test_find_target_line_fallback_scan():
    text_lines = ["line1\n", "target text here\n", "line3\n"]
    finding = {"original": "target text here", "location": "15行目"}
    assert find_target_line(text_lines, finding) == 2


def test_find_target_line_not_found():
    text_lines = ["line1\n", "line2\n"]
    finding = {"original": "not found", "location": "1行目"}
    assert find_target_line(text_lines, finding) is None


def test_find_target_line_empty_original():
    text_lines = ["line1\n"]
    finding = {"original": "", "location": "1"}
    assert find_target_line(text_lines, finding) is None


def test_find_target_line_multi_line():
    text_lines = ["line1\n", "first part of text\n", "second part of text\n", "line4\n"]
    finding = {"original": "first part of text\nsecond part of text", "location": "2"}
    assert find_target_line(text_lines, finding) == 2


def test_find_target_line_stripped_match():
    text_lines = ["  spaced line text  \n"]
    finding = {"original": "spaced line text", "location": "1"}
    assert find_target_line(text_lines, finding) == 1


def test_find_target_line_fuzzy_match():
    # Test matching where spaces, indents, or newline types might differ slightly
    text_lines = [
        "Chapter 1\n",
        "  This is a   long text\n",
        "with different spacing.\n",
    ]
    finding = {
        "original": "This is a long text\nwith different spacing.",
        "location": "2",
    }
    assert find_target_line(text_lines, finding) == 2


def test_query_llm_for_block_replacement_generic_exception():
    mock_task = MagicMock()
    mock_task.execute.side_effect = Exception("Generic LLM failure")

    with patch("src.findings.replacer.BlockReplacementTask", return_value=mock_task):
        res = query_llm_for_block_replacement(["line1"], [], "model")
        assert res is None


def test_interactive_choice_edit():
    finding = {"id": "INT-001", "suggestion": "「元の文」を「修正後」に。"}
    with patch("builtins.input", side_effect=["e", "修正後"]):
        choice = _interactive_choice(finding)
        assert choice == "e"
        assert finding["accepted"] == "y"
        assert finding["suggestion"] == "「修正後」に修正してください。"


def test_interactive_choice_no():
    finding = {"id": "INT-001", "suggestion": "提案", "accepted": None}
    with patch("builtins.input", return_value="n"):
        choice = _interactive_choice(finding)
        assert choice == "n"
        assert finding["accepted"] is None


def test_determine_accepted_findings_target_not_found():
    findings = [
        {"id": "INT-001", "accepted": "y", "original": "not found", "location": "1"}
    ]
    text_lines = ["line1"]

    args = MagicMock()
    args.accept_ids = None
    args.auto = True

    active = _determine_accepted_findings(findings, text_lines, args)
    assert len(active) == 0
    assert findings[0]["apply_status"] == "failed"


def test_main_empty_findings(tmp_path):
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text("content", encoding="utf-8")

    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    findings_yaml_path.write_text("findings: []", encoding="utf-8")

    test_args = ["apply_findings.py", "--dir", str(tmp_path), "--auto"]
    with patch("sys.argv", test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0


def test_main_default_to_interactive(tmp_path):
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text("content", encoding="utf-8")

    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    findings_yaml_path.write_text(
        "findings:\n  - id: INT-001\n    original: content", encoding="utf-8"
    )

    test_args = ["apply_findings.py", "--dir", str(tmp_path)]
    with (
        patch("sys.argv", test_args),
        patch(
            "src.apply_findings._determine_accepted_findings", return_value=[]
        ) as mock_determine,
        patch("src.apply_findings._save_outputs_and_print_summary"),
    ):
        main()
        mock_determine.assert_called_once()
        args = mock_determine.call_args[0][2]
        assert args.interactive is True


def test_save_outputs_yaml_exception(tmp_path):
    stats = (0, 0, 0)
    real_open = builtins.open

    def mock_open(file, *args, **kwargs):
        if "dummy.yaml" in str(file):
            raise Exception("YAML write failed")
        return real_open(tmp_path / "dummy.txt", *args, **kwargs)

    with patch("builtins.open", mock_open):
        _save_outputs_and_print_summary(
            str(tmp_path / "dummy.txt"), "dummy.yaml", [], [], stats
        )


def test_find_target_line_robust_multi_line_and_fuzzy():
    text_lines = [
        "泥と汗で硬くなった作業着が、歩くたびに太ももを擦る。\n",
        "入り口に立ちはだかったのは、分厚い獣皮の外套をまとった二人の男だ。\n",
        "胸元には天秤の紋章が揺れている。\n",
        "男は蔑むように鼻で笑うと、汚れた指先でカップの縁を小突く。\n",
    ]

    # 複数行かつ一部が「カップ of 縁」になっているケース
    finding = {
        "original": "入り口に立ちはだかったのは、分厚い獣皮の外套をまとった二人の男だ。\n蔑むように鼻で笑うと、汚れた指先でカップ of 縁を小突く。",
        "location": "2行目、4行目",
    }

    line_no = find_target_line(text_lines, finding)
    assert line_no == 2
    assert "_matched_lines" in finding
    assert finding["_matched_lines"] == [2, 4]


def test_apply_grouped_findings_context_extension():
    # _apply_grouped_findings が _matched_lines を考慮することを確認
    from src.findings.applier import _apply_grouped_findings

    text_lines = [
        "L1\n",
        "L2\n",
        "L3\n",
        "L4\n",
        "L5\n",
        "L6\n",
    ]

    finding = {
        "id": "INT-001",
        "original": "L2\nL5",
        "suggestion": "「L2」を「L2改」に、「L5」を「L5改」に",
        "_matched_lines": [2, 5],
    }

    # group: list[list[tuple[int, dict]]]
    # 各 tuple は (line_no, finding)
    groups = [[(2, finding)]]

    args = MagicMock()
    args.no_llm = True  # fallback to block をトリガーさせる

    # apply_fallback_to_block をパッチして、引数 context_lines をアサートする
    expected_context = list(text_lines)
    with patch(
        "src.findings.applier.apply_fallback_to_block", return_value=("", [], [])
    ) as mock_fallback:
        _apply_grouped_findings(text_lines, groups, args)
        mock_fallback.assert_called_once()
        context_lines = mock_fallback.call_args[0][0]
        # L_min = 2, L_max = 5 (from _matched_lines)
        # C = 4
        # start_idx = max(0, 2 - 1 - 4) = 0
        # end_idx = min(6, 5 + 4) = 6
        assert len(context_lines) == 6
        assert context_lines == expected_context
