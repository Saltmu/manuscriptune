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
        patch("src.utils.ai_tasks.writing.read_file", return_value="dummy content"),
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


def test_get_neighboring_episodes_plots():
    import writer_cli

    mock_plot_data = [
        {
            "title": "第1章 プロット",
            "episodes": [
                {
                    "title": "第1話",
                    "name": "圧し潰す水色の朝",
                    "content": ["【テーマ】\nテーマ1", "シーン1"],
                },
                {
                    "title": "第2話",
                    "name": "鉄根の昆布採取",
                    "content": ["【テーマ】\nテーマ2", "シーン2"],
                },
                {
                    "title": "第3話",
                    "name": "配給と格差",
                    "content": ["【テーマ】\nテーマ3", "シーン3"],
                },
            ],
        }
    ]

    with (
        patch("os.path.exists", return_value=True),
        patch("writer_cli.writer_helper.parse_plot", return_value=mock_plot_data),
    ):
        # 第2話を指定した場合、前話(第1話)と後話(第3話)が取得できる
        prev_p, next_p = writer_cli.get_neighboring_episodes_plots("dummy.txt", "第2話")
        assert prev_p is not None
        assert next_p is not None
        assert "第1話" in prev_p["title"]
        assert "テーマ1" in prev_p["content"]
        assert "第3話" in next_p["title"]
        assert "テーマ3" in next_p["content"]

        # 第1話を指定した場合、前話はNone、後話(第2話)が取得できる
        prev_p, next_p = writer_cli.get_neighboring_episodes_plots("dummy.txt", "第1話")
        assert prev_p is None
        assert next_p is not None
        assert "第2話" in next_p["title"]

        # 存在しないエピソードを指定した場合、両方None
        prev_p, next_p = writer_cli.get_neighboring_episodes_plots(
            "dummy.txt", "存在しない話"
        )
        assert prev_p is None
        assert next_p is None


def test_writer_cli_with_neighbor_plots():
    import writer_cli

    mock_plot_data = [
        {
            "title": "第1章 プロット",
            "episodes": [
                {
                    "title": "第1話",
                    "name": "ep1",
                    "content": ["前話のプロット"],
                },
                {
                    "title": "第2話",
                    "name": "ep2",
                    "content": ["今話のプロット"],
                },
                {
                    "title": "第3話",
                    "name": "ep3",
                    "content": ["後話のプロット"],
                },
            ],
        }
    ]

    with (
        patch(
            "sys.argv",
            [
                "writer_cli.py",
                "--episode",
                "第2話",
                "--include-neighbor-plots",
                "--prompt-only",
            ],
        ),
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
        patch("src.utils.ai_tasks.writing.read_file", return_value="dummy content"),
        patch("writer_cli.get_previous_episode_file", return_value=None),
        patch("builtins.print") as mock_print,
        pytest.raises(SystemExit) as exc_info,
    ):
        writer_cli.main()

        assert exc_info.value.code == 0

        printed_args = [call[0][0] for call in mock_print.call_args_list]
        combined_output = "\n".join(printed_args)
        assert "【関連エピソードのプロット（参考情報）】" in combined_output
        assert "◆ 前話のプロット：第1章 第1話" in combined_output
        assert "前話のプロット" in combined_output
        assert "◆ 後話のプロット：第1章 第3話" in combined_output
        assert "後話のプロット" in combined_output
        assert "今話のプロット" in combined_output
