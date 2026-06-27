import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is in sys.path so integrate_findings can be imported during tests
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from src.run_review_pipeline import (
    _resolve_output_dir,
    _run_step_format,
    _run_step_integration,
    _run_step_parallel_reviews,
    _run_step_server,
    archive_previous_review,
    main,
    run_filter_context,
    run_formatter,
    run_single_review_skill,
)
from src.utils.ai_client import AgyClientError


def test_resolve_output_dir(tmp_path):
    target_file = tmp_path / "novels" / "episode_1.txt"
    os.makedirs(target_file.parent, exist_ok=True)
    target_file.touch()

    # Case 1: dir is None, output directory defaults to novel_check_results/{basename}
    basename, output_dir = _resolve_output_dir(target_file, None)
    assert basename == "episode_1"
    assert output_dir == os.path.join("novel_check_results", "episode_1")

    # Case 2: dir is specified
    custom_dir = str(tmp_path / "custom_results")
    basename, output_dir = _resolve_output_dir(target_file, custom_dir)
    assert basename == "episode_1"
    assert output_dir == custom_dir


def test_archive_previous_review(tmp_path):
    basename = "episode_1"
    output_dir = tmp_path / "novel_check_results" / basename
    os.makedirs(output_dir, exist_ok=True)

    # Place mock files to archive
    formatted_txt = output_dir / f"{basename}_formatted.txt"
    findings_yaml = output_dir / f"{basename}_findings.yaml"
    report_md = output_dir / f"{basename}_report.md"
    filtered_ctx = output_dir / "01_filtered_context.txt"

    formatted_txt.write_text("formatted text contents", encoding="utf-8")
    findings_yaml.write_text("findings yaml contents", encoding="utf-8")
    report_md.write_text("report markdown contents", encoding="utf-8")
    filtered_ctx.write_text("filtered context contents", encoding="utf-8")

    # Perform first archive
    archive_previous_review(str(output_dir), basename)

    # Verify history directory and archived files
    history_dir = output_dir / "history"
    assert os.path.exists(history_dir)
    assert os.path.exists(history_dir / f"v1_{basename}_formatted.txt")
    assert os.path.exists(history_dir / f"v1_{basename}_findings.yaml")
    assert os.path.exists(history_dir / f"v1_{basename}_report.md")
    assert os.path.exists(history_dir / "v1_filtered_context.txt")

    # Perform second archive (recreate findings file so archive isn't skipped)
    findings_yaml.write_text("findings yaml contents v2", encoding="utf-8")
    archive_previous_review(str(output_dir), basename)
    assert os.path.exists(history_dir / f"v2_{basename}_formatted.txt")


def test_run_formatter_fallback(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("Hello [1] World (2) 【3】!  ", encoding="utf-8")
    output_file = tmp_path / "output.txt"

    # Only mock the formatter script path as non-existent to trigger fallback
    real_exists = os.path.exists

    def mock_exists(path):
        if "novel_formatter_helper.py" in str(path):
            return False
        return real_exists(path)

    with patch("os.path.exists", mock_exists):
        run_formatter(str(input_file), str(output_file))

    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "Hello  World  !  "


def test_run_formatter_script(tmp_path):
    input_file = tmp_path / "input.txt"
    output_file = tmp_path / "output.txt"

    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        run_formatter(str(input_file), str(output_file))
        mock_run.assert_called_once()


def test_run_filter_context_not_found(tmp_path):
    with patch("os.path.exists", return_value=False):
        res = run_filter_context("formatted.txt", "output.txt")
        assert res is False


def test_run_filter_context_success(tmp_path):
    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        res = run_filter_context("formatted.txt", "output.txt")
        assert res is True
        mock_run.assert_called_once()


def test_run_filter_context_fail(tmp_path):
    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error info"
        res = run_filter_context("formatted.txt", "output.txt")
        assert res is False


def test_run_single_review_skill_success(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.return_value = "yaml: data"

    with patch(
        "src.run_review_pipeline.ReviewSkillTask", return_value=mock_task_instance
    ):
        skill, success, msg = run_single_review_skill(
            "dummy-skill", "text", str(output_file), "model", str(tmp_path)
        )
        assert skill == "dummy-skill"
        assert success is True
        assert output_file.read_text(encoding="utf-8") == "yaml: data\n"


def test_run_single_review_skill_client_error(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.side_effect = AgyClientError("API failed")

    with patch(
        "src.run_review_pipeline.ReviewSkillTask", return_value=mock_task_instance
    ):
        skill, success, msg = run_single_review_skill(
            "dummy-skill", "text", str(output_file), "model", str(tmp_path)
        )
        assert success is False
        assert "API failed" in msg


def test_run_single_review_skill_generic_error(tmp_path):
    output_file = tmp_path / "output.yaml"
    mock_task_instance = MagicMock()
    mock_task_instance.execute.side_effect = Exception("Unexpected error")

    with patch(
        "src.run_review_pipeline.ReviewSkillTask", return_value=mock_task_instance
    ):
        skill, success, msg = run_single_review_skill(
            "dummy-skill", "text", str(output_file), "model", str(tmp_path)
        )
        assert success is False
        assert "Unexpected error" in msg


def test_run_step_format_rereview(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    findings_file = output_dir / "episode_findings.yaml"
    findings_file.touch()

    with patch("src.run_review_pipeline.archive_previous_review") as mock_archive:
        _run_step_format(Path("dummy.txt"), "formatted.txt", str(output_dir), "episode")
        mock_archive.assert_called_once_with(str(output_dir), "episode")


def test_run_step_format_not_exists_success(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    formatted_draft = output_dir / "formatted.txt"

    with patch("src.run_review_pipeline.run_formatter") as mock_formatter:
        _run_step_format(
            Path("dummy.txt"), str(formatted_draft), str(output_dir), "episode"
        )
        mock_formatter.assert_called_once_with("dummy.txt", str(formatted_draft))


def test_run_step_format_not_exists_error(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    formatted_draft = output_dir / "formatted.txt"

    with patch(
        "src.run_review_pipeline.run_formatter", side_effect=Exception("Failed")
    ):
        with pytest.raises(SystemExit) as excinfo:
            _run_step_format(
                Path("dummy.txt"), str(formatted_draft), str(output_dir), "episode"
            )
        assert excinfo.value.code == 1


def test_run_step_format_already_exists(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    formatted_draft = output_dir / "formatted.txt"
    formatted_draft.touch()

    with patch("src.run_review_pipeline.run_formatter") as mock_formatter:
        _run_step_format(
            Path("dummy.txt"), str(formatted_draft), str(output_dir), "episode"
        )
        mock_formatter.assert_not_called()


def test_run_step_parallel_reviews(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("src.run_review_pipeline.run_single_review_skill") as mock_run_skill:
        mock_run_skill.side_effect = [
            ("text-reviewer-logic", True, "success"),
            ("text-reviewer-style", False, "failed"),
            ("text-reviewer-logic", True, "success"),
        ]
        _run_step_parallel_reviews("target text", str(output_dir), "model", 2)
        assert mock_run_skill.call_count >= 2


def test_run_step_integration_success(tmp_path):
    with patch(
        "integrate_findings.integrate_findings_in_dir", return_value=True
    ) as mock_integrate:
        _run_step_integration(str(tmp_path), "episode", "model")
        mock_integrate.assert_called_once_with(str(tmp_path), "model")


def test_run_step_integration_fail(tmp_path):
    with patch(
        "integrate_findings.integrate_findings_in_dir", return_value=False
    ) as mock_integrate:
        _run_step_integration(str(tmp_path), "episode", "model")
        mock_integrate.assert_called_once_with(str(tmp_path), "model")


def test_run_step_integration_error(tmp_path):
    with patch(
        "integrate_findings.integrate_findings_in_dir", side_effect=Exception("Error")
    ) as mock_integrate:
        _run_step_integration(str(tmp_path), "episode", "model")
        mock_integrate.assert_called_once_with(str(tmp_path), "model")


def test_run_step_server_no_server():
    with patch("subprocess.run") as mock_run:
        _run_step_server("formatted.txt", "output_dir", "episode", no_server=True)
        mock_run.assert_not_called()


def test_run_step_server_not_found():
    with (
        patch("os.path.exists", return_value=False),
        patch("subprocess.run") as mock_run,
    ):
        _run_step_server("formatted.txt", "output_dir", "episode", no_server=False)
        mock_run.assert_not_called()


def test_run_step_server_found():
    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.run") as mock_run,
    ):
        _run_step_server("formatted.txt", "output_dir", "episode", no_server=False)
        mock_run.assert_called_once()


@patch("src.run_review_pipeline._run_step_format")
@patch("src.run_review_pipeline.run_filter_context")
@patch("src.run_review_pipeline._run_step_parallel_reviews")
@patch("src.run_review_pipeline._run_step_integration")
@patch("src.run_review_pipeline._run_step_server")
@patch("src.run_review_pipeline.read_file", return_value="novel text")
@patch("src.run_review_pipeline.os.makedirs")
def test_main(
    mock_makedirs,
    mock_read_file,
    mock_server,
    mock_integration,
    mock_reviews,
    mock_filter,
    mock_format,
):
    test_args = [
        "run_review_pipeline.py",
        "novels/episode_1.txt",
        "--model",
        "test-model",
    ]
    with patch("sys.argv", test_args):
        main()

    mock_format.assert_called_once()
    mock_filter.assert_called_once()
    mock_reviews.assert_called_once()
    mock_integration.assert_called_once()
    mock_server.assert_called_once()
