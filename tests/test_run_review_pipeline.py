import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.run_review_pipeline import main
from src.services.pipeline_service import TextReviewPipeline
from src.utils.ai_client import AgyClientError
from src.utils.ai_exceptions import (
    ContextFilteringError,
    FormattingError,
    IntegrationError,
    PipelineError,
    ReviewSkillExecutionError,
)
from src.utils.project_paths import DEFAULT_RESULTS_DIR


def test_resolve_output_dir(tmp_path):
    target_file = tmp_path / "novels" / "episode_1.txt"
    pipeline = TextReviewPipeline(str(target_file))
    assert pipeline.basename == "episode_1"
    assert pipeline.output_dir == os.path.join(DEFAULT_RESULTS_DIR, "episode_1")

    # Smart resolution when defaults result dir is in path
    target_in_results = tmp_path / DEFAULT_RESULTS_DIR / "my_story" / "chapter_2.txt"
    pipeline2 = TextReviewPipeline(str(target_in_results))
    assert pipeline2.basename == "my_story"
    assert pipeline2.output_dir == os.path.join(DEFAULT_RESULTS_DIR, "my_story")


def test_archive_previous_review(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    findings_file = output_dir / "episode_findings.yaml"
    findings_file.touch()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    # Files to archive
    formatted_file = output_dir / "episode_formatted.txt"
    formatted_file.touch()
    report_file = output_dir / "episode_report.md"
    report_file.touch()
    context_file = output_dir / "01_filtered_context.txt"
    context_file.touch()

    pipeline.archive_previous_review(target_path=Path("dummy.txt"))

    # Assert archive exists
    archive_dir = output_dir / "history" / "v1"
    assert archive_dir.exists()
    assert (archive_dir / "episode_formatted.txt").exists()
    assert (archive_dir / "episode_findings.yaml").exists()
    assert (archive_dir / "episode_report.md").exists()
    assert (archive_dir / "01_filtered_context.txt").exists()

    # Original files deleted
    assert not findings_file.exists()
    assert not report_file.exists()


def test_run_formatter_not_found(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("Hello[1] World!", encoding="utf-8")
    output_file = tmp_path / "output.txt"

    pipeline = TextReviewPipeline("dummy.txt")

    original_exists = os.path.exists

    def side_effect(path):
        if "novel_formatter_helper.py" in str(path):
            return False
        return original_exists(path)

    with patch("os.path.exists", side_effect=side_effect):
        pipeline.run_formatter(str(input_file), str(output_file))
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == "Hello World!"


def test_run_formatter_success(tmp_path):
    input_file = tmp_path / "input.txt"
    output_file = tmp_path / "output.txt"

    mock_runner = MagicMock()
    pipeline = TextReviewPipeline("dummy.txt", runner=mock_runner)

    with patch("os.path.exists", return_value=True):
        pipeline.run_formatter(str(input_file), str(output_file))
        mock_runner.run.assert_called_once()


def test_run_filter_context_not_found(tmp_path):
    pipeline = TextReviewPipeline("dummy.txt")
    with patch("os.path.exists", return_value=False):
        res = pipeline.run_filter_context("formatted.txt", "output.txt")
        assert res is None


def test_run_filter_context_success(tmp_path):
    mock_runner = MagicMock()
    pipeline = TextReviewPipeline("dummy.txt", runner=mock_runner)

    with patch("os.path.exists", return_value=True):
        pipeline.run_filter_context("formatted.txt", "output.txt")
        mock_runner.run.assert_called_once()


def test_run_filter_context_fail(tmp_path):
    mock_runner = MagicMock()
    mock_runner.run.side_effect = PipelineError("Command failed")
    pipeline = TextReviewPipeline("dummy.txt", runner=mock_runner)

    with patch("os.path.exists", return_value=True):
        with pytest.raises(ContextFilteringError):
            pipeline.run_filter_context("formatted.txt", "output.txt")


def test_run_single_review_skill_success(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.return_value = "yaml: data"

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch(
        "src.pipeline.phase_review.ReviewSkillTask", return_value=mock_task_instance
    ):
        skill, success, msg = pipeline.run_single_review_skill(
            "dummy-skill", "text", str(output_file)
        )
        assert skill == "dummy-skill"
        assert success is True
        assert output_file.read_text(encoding="utf-8") == "yaml: data\n"


def test_run_single_review_skill_client_error(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.side_effect = AgyClientError("API failed")

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch(
        "src.pipeline.phase_review.ReviewSkillTask", return_value=mock_task_instance
    ):
        with pytest.raises(ReviewSkillExecutionError) as excinfo:
            pipeline.run_single_review_skill("dummy-skill", "text", str(output_file))
        assert "dummy-skill" in str(excinfo.value)
        assert "API failed" in str(excinfo.value.__cause__)


def test_run_single_review_skill_generic_error(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.side_effect = Exception("Unexpected error")

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))

    with patch(
        "src.pipeline.phase_review.ReviewSkillTask", return_value=mock_task_instance
    ):
        with pytest.raises(ReviewSkillExecutionError) as excinfo:
            pipeline.run_single_review_skill("dummy-skill", "text", str(output_file))
        assert "dummy-skill" in str(excinfo.value)
        assert "Unexpected error" in str(excinfo.value.__cause__)


def test_run_step_format_rereview(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    findings_file = output_dir / "episode_findings.yaml"
    findings_file.touch()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    with (
        patch.object(pipeline, "archive_previous_review") as mock_archive,
        patch.object(pipeline, "run_formatter"),
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
    ):
        pipeline.execute(no_server=True)
        mock_archive.assert_called_once_with(target_path=Path("dummy.txt"))


def test_run_step_format_not_exists_success(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    with (
        patch.object(pipeline, "run_formatter") as mock_formatter,
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
    ):
        pipeline.execute(no_server=True)
        formatted_draft = os.path.join(str(output_dir), "episode_formatted.txt")
        mock_formatter.assert_called_once_with("dummy.txt", formatted_draft)


def test_run_step_format_not_exists_error(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    with patch.object(pipeline, "run_formatter", side_effect=FormattingError("Failed")):
        with pytest.raises(FormattingError):
            pipeline.execute(no_server=True)


def test_run_step_format_already_exists(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    formatted_draft = output_dir / "episode_formatted.txt"
    formatted_draft.touch()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    with (
        patch.object(pipeline, "run_formatter") as mock_formatter,
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
    ):
        pipeline.execute(no_server=True)
        mock_formatter.assert_not_called()


def test_run_step_parallel_reviews(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))

    with patch.object(pipeline, "run_single_review_skill") as mock_run_skill:
        mock_run_skill.side_effect = [
            ("text-reviewer-logic", True, "success"),
            ("text-reviewer-style", False, "failed"),
        ]
        pipeline.run_parallel_review_skills(
            "target text", {"text-reviewer-logic": "02_logic.yaml"}
        )
        assert mock_run_skill.call_count >= 1


def test_run_step_integration_success(tmp_path):
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))
    with patch(
        "src.integrate_findings.integrate_findings_in_dir", return_value=True
    ) as mock_integrate:
        pipeline._integrate_findings()
        mock_integrate.assert_called_once_with(str(tmp_path), pipeline.model)


def test_run_step_integration_fail(tmp_path):
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))
    with patch(
        "src.integrate_findings.integrate_findings_in_dir", return_value=False
    ) as mock_integrate:
        with pytest.raises(IntegrationError):
            pipeline._integrate_findings()
        mock_integrate.assert_called_once_with(str(tmp_path), pipeline.model)


def test_run_step_integration_error(tmp_path):
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(tmp_path))
    with patch(
        "src.integrate_findings.integrate_findings_in_dir",
        side_effect=Exception("Error"),
    ) as mock_integrate:
        with pytest.raises(IntegrationError):
            pipeline._integrate_findings()
        mock_integrate.assert_called_once_with(str(tmp_path), pipeline.model)


def test_run_step_server_no_server(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    mock_runner = MagicMock()
    pipeline.runner = mock_runner

    original_exists = os.path.exists

    def side_effect(path):
        if "review_server.py" in str(path):
            return True
        if "episode_findings.yaml" in str(path):
            return False
        return original_exists(path)

    with (
        patch("os.path.exists", side_effect=side_effect),
        patch.object(pipeline, "run_formatter"),
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
        patch("src.services.pipeline_service.read_file", return_value="dummy"),
    ):
        pipeline.execute(no_server=True)
        mock_runner.run.assert_not_called()


def test_run_step_server_not_found(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    mock_runner = MagicMock()
    pipeline.runner = mock_runner

    original_exists = os.path.exists

    def side_effect(path):
        if "review_server.py" in str(path):
            return False
        if "episode_findings.yaml" in str(path):
            return False
        return original_exists(path)

    with (
        patch("os.path.exists", side_effect=side_effect),
        patch.object(pipeline, "run_formatter"),
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
        patch("src.services.pipeline_service.read_file", return_value="dummy"),
    ):
        pipeline.execute(no_server=False)
        mock_runner.run.assert_not_called()


def test_run_step_server_found(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    pipeline = TextReviewPipeline("dummy.txt", output_dir_override=str(output_dir))
    pipeline.basename = "episode"

    mock_runner = MagicMock()
    pipeline.runner = mock_runner

    original_exists = os.path.exists

    def side_effect(path):
        if "review_server.py" in str(path):
            return True
        if "episode_findings.yaml" in str(path):
            return False
        return original_exists(path)

    with (
        patch("os.path.exists", side_effect=side_effect),
        patch.object(pipeline, "run_formatter"),
        patch.object(pipeline, "run_filter_context"),
        patch.object(pipeline, "run_parallel_review_skills"),
        patch.object(pipeline, "_integrate_findings"),
        patch("src.services.pipeline_service.read_file", return_value="dummy"),
    ):
        pipeline.execute(no_server=False)
        mock_runner.run.assert_called_once()


def test_main_success(tmp_path):
    novel_file = tmp_path / "novel.txt"
    novel_file.write_text("小説の本文", encoding="utf-8")

    test_args = [
        "run_review_pipeline.py",
        str(novel_file),
        "--dir",
        str(tmp_path / "out"),
        "--no-server",
    ]

    mock_pipeline_execute = MagicMock()

    with (
        patch("sys.argv", test_args),
        patch("src.run_review_pipeline.TextReviewPipeline") as mock_pipeline_class,
    ):
        mock_pipeline_class.return_value.execute = mock_pipeline_execute
        main()

    mock_pipeline_class.assert_called_once_with(
        target_file=str(novel_file),
        model="Gemini 3.5 Flash (High)",
        output_dir_override=str(tmp_path / "out"),
        workers=2,
    )
    mock_pipeline_execute.assert_called_once_with(no_server=True)
