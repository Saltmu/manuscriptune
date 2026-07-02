import os
from unittest.mock import MagicMock, patch

import pytest

from src.run_plot_review_pipeline import main
from src.services.pipeline_service import PlotReviewPipeline
from src.utils.ai_client import AgyClientError
from src.utils.ai_exceptions import (
    ReviewSkillExecutionError,
)
from src.utils.project_paths import DEFAULT_RESULTS_DIR


def test_archive_previous_plot_review(tmp_path):
    basename = "plot1"
    output_dir = tmp_path / DEFAULT_RESULTS_DIR / basename
    os.makedirs(output_dir, exist_ok=True)

    findings_yaml = output_dir / f"{basename}_plot_findings.yaml"
    report_md = output_dir / f"{basename}_plot_report.md"

    findings_yaml.write_text("findings yaml contents", encoding="utf-8")
    report_md.write_text("report markdown contents", encoding="utf-8")

    pipeline = PlotReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = basename

    # Perform first archive
    pipeline.archive_previous_review()

    history_dir = output_dir / "history"
    assert os.path.exists(history_dir)
    assert os.path.exists(history_dir / f"v1_{basename}_plot_findings.yaml")
    assert os.path.exists(history_dir / f"v1_{basename}_plot_report.md")

    # Perform second archive
    findings_yaml.write_text("findings yaml contents v2", encoding="utf-8")
    pipeline.archive_previous_review()
    assert os.path.exists(history_dir / f"v2_{basename}_plot_findings.yaml")


def test_run_single_review_skill_success(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.return_value = "findings: []"

    pipeline = PlotReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch("src.pipeline.phase_review.ReviewSkillTask", mock_task):
        skill, success, msg = pipeline.run_single_review_skill(
            "plot-reviewer-conflict", "plot text", str(output_file)
        )
        assert skill == "plot-reviewer-conflict"
        assert success is True
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == "findings: []\n"


def test_run_single_review_skill_agy_error(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.side_effect = AgyClientError("Agy error")

    pipeline = PlotReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch("src.pipeline.phase_review.ReviewSkillTask", mock_task):
        with pytest.raises(ReviewSkillExecutionError) as excinfo:
            pipeline.run_single_review_skill(
                "plot-reviewer-conflict", "plot text", str(output_file)
            )
        assert "plot-reviewer-conflict" in str(excinfo.value)
        assert "Agy error" in str(excinfo.value.__cause__)


def test_run_single_review_skill_unexpected_error(tmp_path):
    output_file = tmp_path / "output.yaml"

    mock_task = MagicMock()
    mock_task.return_value.execute.side_effect = Exception("Unexpected")

    pipeline = PlotReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch("src.pipeline.phase_review.ReviewSkillTask", mock_task):
        with pytest.raises(ReviewSkillExecutionError) as excinfo:
            pipeline.run_single_review_skill(
                "plot-reviewer-conflict", "plot text", str(output_file)
            )
        assert "plot-reviewer-conflict" in str(excinfo.value)
        assert "Unexpected" in str(excinfo.value.__cause__)


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

    mock_pipeline_execute = MagicMock()

    with patch("sys.argv", test_args):
        with patch(
            "src.run_plot_review_pipeline.PlotReviewPipeline"
        ) as mock_pipeline_class:
            mock_pipeline_class.return_value.execute = mock_pipeline_execute
            main()

    mock_pipeline_class.assert_called_once_with(
        target_file=str(plot_file),
        model="Gemini 3.5 Flash (High)",
        output_dir_override=str(tmp_path / "out"),
        workers=2,
    )
    mock_pipeline_execute.assert_called_once()
