import os
import sys
from unittest.mock import patch

import pytest

# Add skill directory to sys.path to import writer_cli despite the hyphen in the folder name
skill_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../skills/novel-writer-antigravitycli")
)
if skill_dir not in sys.path:
    sys.path.insert(0, skill_dir)


def test_writer_cli_prompt_only():
    import writer_cli

    with (
        patch("sys.argv", ["writer_cli.py", "--episode", "第1話", "--prompt-only"]),
        patch(
            "writer_cli.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "writer_cli.writer_service.WriterService.generate_prompt",
            return_value="Generated Prompt Content",
        ) as mock_generate,
        patch("builtins.print") as mock_print,
        pytest.raises(SystemExit) as exc_info,
    ):
        writer_cli.main()

    assert exc_info.value.code == 0
    mock_generate.assert_called_once()
    printed_args = [call[0][0] for call in mock_print.call_args_list]
    assert "Generated Prompt Content" in printed_args


def test_writer_cli_execute_delegates_to_service():
    import writer_cli

    with (
        patch("sys.argv", ["writer_cli.py", "--episode", "第1話", "--step-by-step"]),
        patch(
            "writer_cli.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "writer_cli.writer_service.WriterService.execute",
            return_value="novels/1_1.txt",
        ) as mock_execute,
    ):
        writer_cli.main()

        mock_execute.assert_called_once()
        _, kwargs = mock_execute.call_args
        assert kwargs["episode"] == "第1話"
        assert kwargs["step_by_step"] is True


def test_writer_cli_execute_error_exits_1():
    import writer_cli

    with (
        patch("sys.argv", ["writer_cli.py", "--episode", "第1話"]),
        patch(
            "writer_cli.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "writer_cli.writer_service.WriterService.execute",
            side_effect=writer_cli.writer_service.WriterServiceError("no plot"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        writer_cli.main()

    assert exc_info.value.code == 1
