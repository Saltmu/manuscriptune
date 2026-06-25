from unittest.mock import MagicMock, patch

from src.integrate_findings import (
    generate_markdown_report,
    integrate_findings_in_dir,
    parse_yaml_file,
    read_file,
)


def test_read_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world", encoding="utf-8")
    assert read_file(str(test_file)) == "hello world"

    assert read_file(None) == ""
    assert read_file(str(tmp_path / "non_existent.txt")) == ""


def test_parse_yaml_file(tmp_path):
    yaml_content_1 = """
findings:
  - id: INT-001
    category: test
"""
    test_file_1 = tmp_path / "yaml1.yaml"
    test_file_1.write_text(yaml_content_1, encoding="utf-8")
    res1 = parse_yaml_file(str(test_file_1))
    assert len(res1) == 1
    assert res1[0]["id"] == "INT-001"

    yaml_content_2 = """
- id: INT-002
  category: test2
"""
    test_file_2 = tmp_path / "yaml2.yaml"
    test_file_2.write_text(yaml_content_2, encoding="utf-8")
    res2 = parse_yaml_file(str(test_file_2))
    assert len(res2) == 1
    assert res2[0]["id"] == "INT-002"

    yaml_content_3 = """
findings:
  - id: INT-003
    [invalid_syntax_here:
"""
    test_file_3 = tmp_path / "yaml3.yaml"
    test_file_3.write_text(yaml_content_3, encoding="utf-8")
    assert parse_yaml_file(str(test_file_3)) == []


def test_generate_markdown_report(tmp_path):
    findings = [
        {
            "id": "INT-001",
            "category": "ロジック矛盾",
            "location": "15行目",
            "original": "古い剣",
            "analysis": "この時点ではまだ手に入れていません。",
            "suggestion": "「木刀」に変更する。",
            "severity": "high",
        },
        {
            "id": "INT-002",
            "category": "誤字",
            "location": "30行目",
            "original": "たいへん",
            "analysis": "タイヘンになっている。",
            "suggestion": "大変にする。",
            "severity": "low",
        },
    ]
    report_file = tmp_path / "report.md"
    generate_markdown_report(findings, str(report_file))

    content = report_file.read_text(encoding="utf-8")
    assert "小説校閲 統合レポート" in content
    assert "INT-001" in content
    assert "木刀" in content
    assert "重大な課題" in content


def test_integrate_findings_in_dir_fallback(tmp_path):
    chapter_dir = tmp_path / "chapter_01"
    chapter_dir.mkdir()

    formatted_txt = chapter_dir / "chapter_01_formatted.txt"
    formatted_txt.write_text("これは小説の本文です。", encoding="utf-8")

    logic_yaml = chapter_dir / "02_logic_consistency.yaml"
    logic_yaml.write_text(
        """
findings:
  - id: LOG-001
    location: 1
    original: 本文
    category: 矛盾
    severity: medium
    analysis: テスト分析
    suggestion: テスト提案
    accepted: "n"
""",
        encoding="utf-8",
    )

    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        success = integrate_findings_in_dir(str(chapter_dir), "Gemini 3.5 Flash")
        assert success is True

        merged_yaml = chapter_dir / "chapter_01_findings.yaml"
        assert merged_yaml.exists()

        report_md = chapter_dir / "chapter_01_report.md"
        assert report_md.exists()

        import yaml

        with open(merged_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert "findings" in data
            assert len(data["findings"]) == 1
            assert data["findings"][0]["id"] == "INT-001"
            assert data["findings"][0]["original"] == "本文"


def test_integrate_findings_in_dir_success(tmp_path):
    chapter_dir = tmp_path / "chapter_01"
    chapter_dir.mkdir()

    formatted_txt = chapter_dir / "chapter_01_formatted.txt"
    formatted_txt.write_text("これは小説の本文です。", encoding="utf-8")

    logic_yaml = chapter_dir / "02_logic_consistency.yaml"
    logic_yaml.write_text(
        """
findings:
  - id: LOG-001
    location: 1
    original: 本文
    category: 矛盾
    severity: medium
    analysis: テスト分析
    suggestion: テスト提案
    accepted: "n"
""",
        encoding="utf-8",
    )

    mock_process = MagicMock()
    mock_process.return_value.communicate.return_value = (
        '```yaml\nfindings:\n  - id: INT-001\n    location: 1\n    original: 本文\n    category: 矛盾\n    severity: medium\n    analysis: LLM統合された分析\n    suggestion: LLM統合された提案\n    accepted: "n"\n```',
        "",
    )
    mock_process.return_value.returncode = 0

    with patch("subprocess.Popen", mock_process):
        success = integrate_findings_in_dir(str(chapter_dir), "Gemini 3.5 Flash")
        assert success is True

        merged_yaml = chapter_dir / "chapter_01_findings.yaml"
        assert merged_yaml.exists()

        import yaml

        with open(merged_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["findings"][0]["analysis"] == "LLM統合された分析"
