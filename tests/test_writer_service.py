from unittest.mock import patch

import pytest

from src.services import writer_service
from src.services.writer_service import WriterService, WriterServiceError


def test_resolve_episode_output_path(tmp_path):
    sources_dir = tmp_path / "data" / "sources"
    sources_dir.mkdir(parents=True)

    plot_content = """第1章：テストの始まり
第1話：プロットタイトル（エピソード名）
シーン1：テスト
"""
    plot_file = sources_dir / "04_1_plot.txt"
    plot_file.write_text(plot_content, encoding="utf-8")

    with (
        patch("src.utils.project_paths.get_sources_dir", return_value=str(sources_dir)),
        patch(
            "src.utils.project_paths.get_novels_dir",
            return_value=str(tmp_path / "novels"),
        ),
    ):
        novel_path, basename = WriterService().resolve_episode_output_path(
            "第1話", plot_file=str(plot_file)
        )
        assert basename == "1_1"
        assert novel_path.replace("\\", "/").endswith("novels/1_1.txt")


def test_resolve_episode_output_path_rejects_plot_file_outside_sources(tmp_path):
    sources_dir = tmp_path / "data" / "sources"
    sources_dir.mkdir(parents=True)

    outside_file = tmp_path / "outside" / "evil.txt"
    outside_file.parent.mkdir(parents=True)
    outside_file.write_text("第1章：無関係\n", encoding="utf-8")

    with (
        patch("src.utils.project_paths.get_sources_dir", return_value=str(sources_dir)),
        patch(
            "src.utils.project_paths.get_novels_dir",
            return_value=str(tmp_path / "novels"),
        ),
    ):
        with pytest.raises(Exception) as excinfo:
            WriterService().resolve_episode_output_path(
                "第1話", plot_file=str(outside_file)
            )
        assert excinfo.value.status_code == 403


def _mock_plot_data():
    return [
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


def test_generate_prompt():
    with (
        patch("os.path.exists", return_value=True),
        patch(
            "src.services.writer_service.plot_parser.parse_plot",
            return_value=_mock_plot_data(),
        ),
        patch(
            "src.services.writer_service.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "src.services.writer_service.project_config.get_novel_setting",
            return_value="重天の調律師",
        ),
        patch("src.services.writer_service.read_file", return_value="dummy content"),
        patch("src.utils.ai_tasks.writing.read_file", return_value="dummy content"),
        patch(
            "src.services.writer_service.get_previous_episode_file", return_value=None
        ),
    ):
        prompt = WriterService().generate_prompt(episode="第1話")

        assert "【超重要指示：ツールの使用禁止】" in prompt
        assert "重天の調律師" in prompt
        assert "第1章 プロット 第1話" in prompt
        assert "シーン1のプロット" in prompt


def test_generate_prompt_missing_plot_content_raises():
    with patch("os.path.exists", return_value=False):
        with pytest.raises(WriterServiceError):
            WriterService().generate_prompt(episode="第1話", plot_file="missing.txt")


def test_get_neighboring_episodes_plots():
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
        patch(
            "src.services.writer_service.plot_parser.parse_plot",
            return_value=mock_plot_data,
        ),
    ):
        prev_p, next_p = writer_service.get_neighboring_episodes_plots(
            "dummy.txt", "第2話"
        )
        assert prev_p is not None
        assert next_p is not None
        assert "第1話" in prev_p["title"]
        assert "テーマ1" in prev_p["content"]
        assert "第3話" in next_p["title"]
        assert "テーマ3" in next_p["content"]

        prev_p, next_p = writer_service.get_neighboring_episodes_plots(
            "dummy.txt", "第1話"
        )
        assert prev_p is None
        assert next_p is not None
        assert "第2話" in next_p["title"]

        prev_p, next_p = writer_service.get_neighboring_episodes_plots(
            "dummy.txt", "存在しない話"
        )
        assert prev_p is None
        assert next_p is None


def test_generate_prompt_with_neighbor_plots():
    mock_plot_data = [
        {
            "title": "第1章 プロット",
            "episodes": [
                {"title": "第1話", "name": "ep1", "content": ["前話のプロット"]},
                {"title": "第2話", "name": "ep2", "content": ["今話のプロット"]},
                {"title": "第3話", "name": "ep3", "content": ["後話のプロット"]},
            ],
        }
    ]

    with (
        patch("os.path.exists", return_value=True),
        patch(
            "src.services.writer_service.plot_parser.parse_plot",
            return_value=mock_plot_data,
        ),
        patch(
            "src.services.writer_service.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch(
            "src.services.writer_service.project_config.get_novel_setting",
            return_value="重天の調律師",
        ),
        patch("src.services.writer_service.read_file", return_value="dummy content"),
        patch("src.utils.ai_tasks.writing.read_file", return_value="dummy content"),
        patch(
            "src.services.writer_service.get_previous_episode_file", return_value=None
        ),
    ):
        prompt = WriterService().generate_prompt(
            episode="第2話", include_neighbor_plots=True
        )

        assert "【関連エピソードのプロット（参考情報）】" in prompt
        assert "◆ 前話のプロット：第1章 プロット 第1話" in prompt
        assert "前話のプロット" in prompt
        assert "◆ 後話のプロット：第1章 プロット 第3話" in prompt
        assert "後話のプロット" in prompt
        assert "今話のプロット" in prompt


def test_execute_writes_novel_file(tmp_path):
    novels_dir = tmp_path / "novels"

    with (
        patch("os.path.exists", return_value=True),
        patch(
            "src.services.writer_service.plot_parser.parse_plot",
            return_value=_mock_plot_data(),
        ),
        patch(
            "src.services.writer_service.project_config.resolve_novel_file_by_pattern",
            return_value="dummy_path.txt",
        ),
        patch("src.services.writer_service.read_file", return_value="dummy content"),
        patch("src.utils.ai_tasks.writing.read_file", return_value="dummy content"),
        patch(
            "src.services.writer_service.get_previous_episode_file", return_value=None
        ),
        patch(
            "src.utils.project_paths.get_novel_path",
            side_effect=lambda name: str(novels_dir / name),
        ),
        patch(
            "src.services.writer_service.NovelWritingTask.execute",
            return_value="生成された本文",
        ),
    ):
        output_path = WriterService().execute(episode="第1話")

        assert output_path == str(novels_dir / "1_1.txt")
        assert (novels_dir / "1_1.txt").read_text(
            encoding="utf-8"
        ) == "生成された本文\n"


def test_execute_missing_plot_content_raises():
    with patch("os.path.exists", return_value=False):
        with pytest.raises(WriterServiceError):
            WriterService().execute(episode="第1話", plot_file="missing.txt")
