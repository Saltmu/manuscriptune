import os

import yaml

from src.findings.integration import (
    BaseFindingsIntegrator,
    IntegrationContext,
    fallback_merge,
    generate_markdown_report,
)


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


class _FakeIntegrator(BaseFindingsIntegrator):
    """Minimal concrete subclass used to exercise BaseFindingsIntegrator.run()
    in isolation, without going through the text/plot CLI modules."""

    def __init__(self, model, *, findings, llm_result, prepare_ok=True):
        super().__init__(model)
        self._findings = findings
        self._llm_result = llm_result
        self._prepare_ok = prepare_ok
        self.report_calls: list[list[dict]] = []

    def _collect_raw_findings(self, output_dir):
        return self._findings

    def _prepare(self, output_dir, **kwargs):
        if not self._prepare_ok:
            return None
        return IntegrationContext(
            target_text="dummy text",
            yaml_path=os.path.join(output_dir, "out.yaml"),
            report_path=os.path.join(output_dir, "out.md"),
        )

    def _run_integration_llm(self, output_dir, target_text, raw_findings_text):
        return self._llm_result

    def _fallback_merge(self, all_findings):
        return "findings: []\n_metadata:\n  fallback_mode: true\n"

    def _generate_markdown_report(self, findings, output_md):
        self.report_calls.append(findings)
        with open(output_md, "w", encoding="utf-8") as f:
            f.write("report")


def test_base_integrator_run_dir_not_exists():
    integrator = _FakeIntegrator("model", findings=[], llm_result=None)
    assert integrator.run("non_existent_dir") is False


def test_base_integrator_run_prepare_fails(tmp_path):
    integrator = _FakeIntegrator(
        "model", findings=[], llm_result=None, prepare_ok=False
    )
    assert integrator.run(str(tmp_path)) is False


def test_base_integrator_run_no_findings_writes_empty(tmp_path):
    integrator = _FakeIntegrator("model", findings=[], llm_result=None)
    assert integrator.run(str(tmp_path)) is True

    assert (tmp_path / "out.yaml").read_text(encoding="utf-8") == "findings: []\n"
    assert (tmp_path / "out.md").exists()
    assert integrator.report_calls == [[]]


def test_base_integrator_run_uses_llm_result(tmp_path):
    integrator = _FakeIntegrator(
        "model",
        findings=[{"id": "X-001"}],
        llm_result="findings:\n  - id: X-001\n",
    )
    assert integrator.run(str(tmp_path)) is True

    content = (tmp_path / "out.yaml").read_text(encoding="utf-8")
    assert "X-001" in content
    assert integrator.report_calls == [[{"id": "X-001"}]]


def test_base_integrator_run_falls_back_when_llm_fails(tmp_path):
    integrator = _FakeIntegrator("model", findings=[{"id": "X-001"}], llm_result=None)
    assert integrator.run(str(tmp_path)) is True

    content = (tmp_path / "out.yaml").read_text(encoding="utf-8")
    assert "fallback_mode: true" in content
