from unittest.mock import patch

import pytest
import yaml

from src.services import findings_service
from src.utils.cancellation import CancellationToken, PipelineCancelledError


def test_apply_findings_in_dir_guardrail_violation(tmp_path):
    sources_dir = tmp_path / "data" / "sources" / "volume1"
    sources_dir.mkdir(parents=True)

    with pytest.raises(findings_service.ApplyFindingsValidationError):
        findings_service.apply_findings_in_dir(str(sources_dir))


def test_apply_findings_in_dir_missing_directory():
    with pytest.raises(findings_service.ApplyFindingsValidationError):
        findings_service.apply_findings_in_dir("/nonexistent/dir")


def test_apply_findings_in_dir_no_findings(tmp_path):
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text("content", encoding="utf-8")
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    findings_yaml_path.write_text("findings: []", encoding="utf-8")

    result = findings_service.apply_findings_in_dir(str(tmp_path), auto=True)

    assert result.applied_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 0


def test_apply_findings_in_dir_success(tmp_path):
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
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    result = findings_service.apply_findings_in_dir(
        str(tmp_path), auto=True, no_llm=True
    )

    assert result.applied_count == 1
    assert result.failed_count == 0

    updated_txt = formatted_txt_path.read_text(encoding="utf-8")
    assert "第１章　重天の調律" in updated_txt


def test_apply_findings_in_dir_failure_raises(tmp_path):
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text("少年は佇んでいた。\n", encoding="utf-8")

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

    with patch(
        "src.services.findings_service._apply_grouped_findings",
        return_value=(0, 1),
    ):
        with pytest.raises(findings_service.ApplyFindingsValidationError):
            findings_service.apply_findings_in_dir(str(tmp_path), auto=True)

    # Original text is untouched since the save step never ran.
    assert formatted_txt_path.read_text(encoding="utf-8") == "少年は佇んでいた。\n"


def test_apply_findings_in_dir_respects_cancellation(tmp_path):
    formatted_txt_content = "第１章\n少年は悲しげな顔をして佇んでいた。\n"
    formatted_txt_path = tmp_path / "01_formatted.txt"
    formatted_txt_path.write_text(formatted_txt_content, encoding="utf-8")

    findings_data = {
        "findings": [
            {
                "id": "INT-001",
                "location": "1行目",
                "original": "第１章",
                "suggestion": "「第一章」に修正してください。",
                "accepted": "y",
            }
        ]
    }
    findings_yaml_path = tmp_path / "00_integrated_findings.yaml"
    with open(findings_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(findings_data, f, allow_unicode=True, default_flow_style=False)

    token = CancellationToken()
    token.cancel()

    with pytest.raises(PipelineCancelledError):
        findings_service.apply_findings_in_dir(
            str(tmp_path), auto=True, no_llm=True, cancel_token=token
        )
