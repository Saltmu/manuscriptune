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

    mock_plot_data = [
        {
            "title": "第1章 プロット",
            "episodes": [
                {
                    "title": "第1話",
                    "name": "ep1",
                    "content": ["シーン1のプロット", "シーン2のプロット"],
                }
            ],
        }
    ]

    with (
        patch("sys.argv", ["writer_cli.py", "--episode", "第1話", "--prompt-only"]),
        patch("os.path.exists", return_value=True),
        patch("writer_cli.writer_helper.parse_plot", return_value=mock_plot_data),
        patch(
            "writer_cli.writer_helper.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "writer_cli.writer_helper.get_novel_setting", return_value="重天の調律師"
        ),
        patch("writer_cli.read_file", return_value="dummy content"),
        patch("writer_cli.get_previous_episode_file", return_value=None),
        patch("builtins.print") as mock_print,
        pytest.raises(SystemExit) as exc_info,
    ):
        writer_cli.main()

        # It should exit with 0
        assert exc_info.value.code == 0

        # Check that the prompt was printed
        printed_args = [call[0][0] for call in mock_print.call_args_list]
        combined_output = "\n".join(printed_args)
        assert "【超重要指示：ツールの使用禁止】" in combined_output
        assert "重天の調律師" in combined_output
        assert "第1章 プロット 第1話" in combined_output
        assert "シーン1のプロット" in combined_output
