import os
from unittest.mock import MagicMock, patch

import pytest

from src.run_plot_review_pipeline import (
    archive_previous_plot_review,
    main,
    run_single_review_skill,
)
from src.utils.ai_client import AgyClientError
from src.utils.project_paths import DEFAULT_RESULTS_DIR


def test_archive_previous_plot_review(tmp_path):
    basename = "plot1"
    output_dir = tmp_path / DEFAULT_RESULTS_DIR / basename
    os.makedirs(output_dir, exist_ok=True)

    findings_yaml = output_dir / f"{basename}_plot_findings.yaml"
    report_md = output_dir / f"{basename}_plot_report.md"

    findings_yaml.write_text("findings yaml contents", encoding="utf-8")
    report_md.write_text("report markdown contents", encoding="utf-8")

    # Perform first archive
    archive_previous_plot_review(str(output_dir), basename)

    history_dir = output_dir / "history"
    assert os.path.exists(history_dir)
    assert os.path.exists(history_dir / f"v1_{basename}_plot_findings.yaml")
    assert os.path.exists(history_dir / f"v1_{basename}_plot_report.md")

    # Perform second archive
    findings_yaml.write_text("findings yaml contents v2", encoding="utf-8")
    archive_previous_plot_review(str(output_dir), basename)
    assert os.path.exists(history_dir / f"v2_{basename}_plot_findings.yaml")


def test_run_single_review_skill_success(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.return_value = "findings: []"

    with patch("src.run_plot_review_pipeline.ReviewSkillTask", mock_task):
        skill, success, msg = run_single_review_skill(
            "plot-reviewer-conflict", "plot text", str(output_file), "model", "dir"
        )
        assert skill == "plot-reviewer-conflict"
        assert success is True
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == "findings: []\n"


def test_run_single_review_skill_agy_error(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.side_effect = AgyClientError("Agy error")

    with patch("src.run_plot_review_pipeline.ReviewSkillTask", mock_task):
        skill, success, msg = run_single_review_skill(
            "plot-reviewer-conflict", "plot text", str(output_file), "model", "dir"
        )
        assert skill == "plot-reviewer-conflict"
        assert success is False
        assert "Agy error" in msg


def test_run_single_review_skill_unexpected_error(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.side_effect = Exception("Unexpected")

    with patch("src.run_plot_review_pipeline.ReviewSkillTask", mock_task):
        skill, success, msg = run_single_review_skill(
            "plot-reviewer-conflict", "plot text", str(output_file), "model", "dir"
        )
        assert skill == "plot-reviewer-conflict"
        assert success is False
        assert "Unexpected" in msg


def test_main_read_plot_failed(tmp_path):
    plot_file = tmp_path / "non_existent.txt"
    test_args = ["run_plot_review_pipeline.py", str(plot_file)]

    with patch("sys.argv", test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_main_success(tmp_path):
    plot_file = tmp_path / "plot.txt"
    plot_file.write_text("プロットの本文", encoding="utf-8")

    test_args = [
        "run_plot_review_pipeline.py",
        str(plot_file),
        "--dir",
        str(tmp_path / "out"),
    ]

    mock_run_skill = MagicMock(return_value=("plot-reviewer-conflict", True, "success"))
    mock_integrate = MagicMock(return_value=True)

    with patch("sys.argv", test_args):
        with patch(
            "src.run_plot_review_pipeline.run_single_review_skill", mock_run_skill
        ):
            with patch(
                "src.integrate_plot_findings.integrate_plot_findings_in_dir",
                mock_integrate,
            ):
                main()

    assert mock_run_skill.call_count == 2
    assert mock_integrate.call_count == 1
