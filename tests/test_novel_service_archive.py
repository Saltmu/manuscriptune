import os
from unittest.mock import patch

from src.services import novel_service


def test_archive_current_state(tmp_path):
    # テスト用ディレクトリの設定
    novels_dir = tmp_path / "novels"
    reviews_dir = tmp_path / "reviews"
    novels_dir.mkdir()
    reviews_dir.mkdir()

    # ダミー小説ファイル
    basename = "1_12"
    novel_file = novels_dir / f"{basename}.txt"
    novel_file.write_text("これは小説の本文です。", encoding="utf-8")

    # レビュー結果のダミーディレクトリとファイル作成
    output_dir = reviews_dir / basename
    output_dir.mkdir(parents=True)

    formatted_file = output_dir / f"{basename}_formatted.txt"
    formatted_file.write_text("これは整形済み本文です。", encoding="utf-8")

    findings_file = output_dir / f"{basename}_findings.yaml"
    findings_file.write_text("findings: []", encoding="utf-8")

    # パス解決のモック
    with (
        patch("src.utils.project_paths.get_novels_dir", return_value=str(novels_dir)),
        patch("src.utils.project_paths.get_output_dir", return_value=str(output_dir)),
    ):
        # 1回目のアーカイブ実行 (v1)
        v1 = novel_service.archive_current_state(
            basename, extra_novel_path=str(novel_file)
        )
        assert v1 == "v1"

        history_v1_dir = reviews_dir / basename / "history" / "v1"
        assert history_v1_dir.exists()
        assert (history_v1_dir / f"{basename}.txt").exists()
        assert (history_v1_dir / f"{basename}_formatted.txt").exists()
        assert (history_v1_dir / f"{basename}_findings.yaml").exists()
        assert (history_v1_dir / f"{basename}.txt").read_text(
            encoding="utf-8"
        ) == "これは小説の本文です。"

        # 2回目のアーカイブ実行 (v2) - 小説の本文を変更してアーカイブ
        novel_file.write_text("これは更新された小説の本文です。", encoding="utf-8")
        v2 = novel_service.archive_current_state(
            basename, extra_novel_path=str(novel_file)
        )
        assert v2 == "v2"

        history_v2_dir = reviews_dir / basename / "history" / "v2"
        assert history_v2_dir.exists()
        assert (history_v2_dir / f"{basename}.txt").exists()
        assert (history_v2_dir / f"{basename}.txt").read_text(
            encoding="utf-8"
        ) == "これは更新された小説の本文です。"


def test_resolve_novel_path_for_write(tmp_path):
    sources_dir = tmp_path / "data" / "sources"
    sources_dir.mkdir(parents=True)

    # ダミープロットファイル
    plot_content = """第1章：テストの始まり
第1話：プロットタイトル（エピソード名）
シーン1：テスト
"""
    plot_file = sources_dir / "04_1_plot.txt"
    plot_file.write_text(plot_content, encoding="utf-8")

    # モック
    with (
        patch("src.utils.project_paths.get_sources_dir", return_value=str(sources_dir)),
        patch(
            "src.utils.project_paths.get_novels_dir",
            return_value=str(tmp_path / "novels"),
        ),
    ):
        novel_path, basename = novel_service.resolve_novel_path_for_write(
            "第1話", plot_file=str(plot_file)
        )
        assert basename == "1_1"
        assert os.path.basename(novel_path) == "1_1.txt"
