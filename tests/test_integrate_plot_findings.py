from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.integrate_plot_findings import (
    _collect_raw_findings,
    generate_markdown_report,
    integrate_plot_findings_in_dir,
    main,
    parse_yaml_file,
    read_file,
    run_integration_llm,
)


def test_read_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello plot", encoding="utf-8")
    assert read_file(str(test_file)) == "hello plot"

    assert read_file(None) == ""
    assert read_file(str(tmp_path / "non_existent.txt")) == ""


def test_parse_yaml_file(tmp_path):
    yaml_content_1 = """
findings:
  - id: PINT-001
    category: test
"""
    test_file_1 = tmp_path / "yaml1.yaml"
    test_file_1.write_text(yaml_content_1, encoding="utf-8")
    res1 = parse_yaml_file(str(test_file_1))
    assert len(res1) == 1
    assert res1[0]["id"] == "PINT-001"

    yaml_content_2 = """
- id: PINT-002
  category: test2
"""
    test_file_2 = tmp_path / "yaml2.yaml"
    test_file_2.write_text(yaml_content_2, encoding="utf-8")
    res2 = parse_yaml_file(str(test_file_2))
    assert len(res2) == 1
    assert res2[0]["id"] == "PINT-002"

    yaml_content_3 = """
findings:
  - id: PINT-003
    [invalid_syntax_here:
"""
    test_file_3 = tmp_path / "yaml3.yaml"
    test_file_3.write_text(yaml_content_3, encoding="utf-8")
    assert parse_yaml_file(str(test_file_3)) == []


def test_generate_markdown_report(tmp_path):
    findings = [
        {
            "id": "PINT-001",
            "category": "停滞シーン",
            "location": "第1章シーン1",
            "original": "何も起きない会話",
            "analysis": "GMCOがすべて欠如しています。",
            "suggestion": "障害と葛藤を追加する。",
            "severity": "high",
        },
        {
            "id": "PINT-002",
            "category": "中だるみ",
            "location": "中盤",
            "original": "移動描写のみ",
            "analysis": "感情の起伏がありません。",
            "suggestion": "外的障害を追加する。",
            "severity": "medium",
        },
    ]
    report_file = tmp_path / "plot_report.md"
    generate_markdown_report(findings, str(report_file))

    content = report_file.read_text(encoding="utf-8")
    assert "プロット構成校閲 統合レポート" in content
    assert "PINT-001" in content
    assert "障害と葛藤" in content
    assert "重大な課題" in content


def test_integrate_plot_findings_in_dir_fallback(tmp_path):
    plot_dir = tmp_path / "plot_result"
    plot_dir.mkdir()

    original_plot = tmp_path / "plot.txt"
    original_plot.write_text("これはプロットの本文です。", encoding="utf-8")

    conflict_yaml = plot_dir / "02_plot_conflict.yaml"
    conflict_yaml.write_text(
        """
findings:
  - id: CA-001
    location: シーン1
    original: プロット
    category: 停滞シーン
    severity: medium
    analysis: テスト分析
    suggestion: テスト提案
    accepted: "n"
""",
        encoding="utf-8",
    )

    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        success = integrate_plot_findings_in_dir(
            str(plot_dir), str(original_plot), "Gemini 3.5 Flash"
        )
        assert success is True

        merged_yaml = plot_dir / "plot_plot_findings.yaml"
        assert merged_yaml.exists()

        report_md = plot_dir / "plot_plot_report.md"
        assert report_md.exists()

        with open(merged_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert "findings" in data
            assert len(data["findings"]) == 1
            assert data["findings"][0]["id"] == "PINT-001"
            assert data["findings"][0]["original"] == "プロット"


def test_integrate_plot_findings_in_dir_success(tmp_path):
    plot_dir = tmp_path / "plot_result"
    plot_dir.mkdir()

    original_plot = tmp_path / "plot.txt"
    original_plot.write_text("これはプロットの本文です。", encoding="utf-8")

    conflict_yaml = plot_dir / "02_plot_conflict.yaml"
    conflict_yaml.write_text(
        """
findings:
  - id: CA-001
    location: シーン1
    original: プロット
    category: 停滞シーン
    severity: medium
    analysis: テスト分析
    suggestion: テスト提案
    accepted: "n"
""",
        encoding="utf-8",
    )

    mock_process = MagicMock()
    mock_process.return_value.communicate.return_value = (
        '```yaml\nfindings:\n  - id: PINT-001\n    location: シーン1\n    original: プロット\n    category: 停滞シーン\n    severity: medium\n    analysis: LLM統合された分析\n    suggestion: LLM統合された提案\n    accepted: "n"\n```',
        "",
    )
    mock_process.return_value.returncode = 0

    with patch("subprocess.Popen", mock_process):
        success = integrate_plot_findings_in_dir(
            str(plot_dir), str(original_plot), "Gemini 3.5 Flash"
        )
        assert success is True

        merged_yaml = plot_dir / "plot_plot_findings.yaml"
        assert merged_yaml.exists()

        with open(merged_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["findings"][0]["analysis"] == "LLM統合された分析"


def test_run_integration_llm_generic_exception():
    mock_task = MagicMock()
    mock_task.execute.side_effect = Exception("General LLM Error")
    with patch(
        "src.integrate_plot_findings.PlotFindingsIntegrationTask",
        return_value=mock_task,
    ):
        res = run_integration_llm("dir", "text", "raw", "model")
        assert res is None


def test_collect_raw_findings_fallback_yamls(tmp_path):
    conflict_yaml = tmp_path / "02_plot_conflict.yaml"
    conflict_yaml.write_text(
        "findings:\n  - id: CA-001\n    original: text", encoding="utf-8"
    )

    findings = _collect_raw_findings(str(tmp_path))
    assert len(findings) == 1
    assert findings[0]["id"] == "CA-001"
    assert findings[0]["_source_file"] == "02_plot_conflict.yaml"


def test_integrate_plot_findings_in_dir_dir_not_exists():
    assert (
        integrate_plot_findings_in_dir("non_existent_dir", "plot_file.txt", "model")
        is False
    )


def test_integrate_plot_findings_in_dir_plot_file_not_exists(tmp_path):
    assert (
        integrate_plot_findings_in_dir(str(tmp_path), "non_existent_plot.txt", "model")
        is False
    )


def test_main_failure():
    with patch(
        "src.integrate_plot_findings.integrate_plot_findings_in_dir",
        return_value=False,
    ):
        test_args = [
            "integrate_plot_findings.py",
            "--dir",
            "dummy_dir",
            "--plot-file",
            "dummy.txt",
        ]
        with patch("sys.argv", test_args):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 1
