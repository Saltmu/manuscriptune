import yaml

from src.findings.integration import fallback_merge, generate_markdown_report


def _report_kwargs(**overrides):
    kwargs = {
        "report_title": "# テストレポート",
        "no_findings_message": "指摘なし",
        "summary_message": "合計 {count} 件です。",
        "severity_titles": {
            "high": "重大",
            "medium": "中程度",
            "low": "軽微",
            "info": "参考",
        },
        "item_label": "対象",
        "suggestion_label": "提案",
        "default_id_prefix": "GEN",
    }
    kwargs.update(overrides)
    return kwargs


def test_generate_markdown_report_empty(tmp_path):
    output_md = tmp_path / "report.md"
    generate_markdown_report([], str(output_md), **_report_kwargs())

    content = output_md.read_text(encoding="utf-8")
    assert "# テストレポート" in content
    assert "指摘なし" in content


def test_generate_markdown_report_uses_overrides(tmp_path):
    findings = [
        {
            "category": "誤字",
            "location": "1行目",
            "original": "元テキスト",
            "analysis": "分析結果",
            "suggestion": "修正案",
            "severity": "high",
        }
    ]
    output_md = tmp_path / "report.md"
    generate_markdown_report(findings, str(output_md), **_report_kwargs())

    content = output_md.read_text(encoding="utf-8")
    assert "合計 1 件です。" in content
    assert "重大" in content
    assert "[GEN]" in content  # default id prefix used since finding has no "id"
    assert "対象" in content
    assert "提案" in content


def test_generate_markdown_report_unknown_severity_falls_back_to_low(tmp_path):
    findings = [{"category": "不明", "severity": "unknown"}]
    output_md = tmp_path / "report.md"
    generate_markdown_report(findings, str(output_md), **_report_kwargs())

    content = output_md.read_text(encoding="utf-8")
    assert "軽微" in content


def test_fallback_merge_assigns_sequential_ids_and_strips_source_file():
    all_findings = [
        {"category": "a", "_source_file": "01.yaml"},
        {"category": "b", "_source_file": "02.yaml"},
    ]
    result = fallback_merge(all_findings, id_prefix="PINT")
    parsed = yaml.safe_load(result)

    assert [f["id"] for f in parsed["findings"]] == ["PINT-001", "PINT-002"]
    assert "_source_file" not in parsed["findings"][0]
    assert "_metadata" not in parsed


def test_fallback_merge_includes_extra_metadata_when_provided():
    result = fallback_merge(
        [{"category": "a"}],
        id_prefix="INT",
        extra_metadata={"fallback_mode": True, "completeness": "low"},
    )
    parsed = yaml.safe_load(result)

    assert parsed["_metadata"]["fallback_mode"] is True
    assert parsed["_metadata"]["completeness"] == "low"
