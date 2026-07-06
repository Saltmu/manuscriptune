from src.utils.plot_parser import get_chapter_episodes, list_chapters, parse_plot


def test_parse_plot(tmp_path):
    # テスト用の一時的なプロットファイルを作成
    plot_content = """
第一章：始まりの光
第一話：旅立ち
これは旅立ちの本文です。

第二話：出会い
旅の途中で新しい仲間に出会いました。
ここも本文です。

幕間一：休息
戦いの合間の静かな時間。

第2章：新たな敵
第3話：強襲
敵が突然現れた。
"""
    plot_file = tmp_path / "test_plot.txt"
    plot_file.write_text(plot_content, encoding="utf-8")

    chapters = parse_plot(str(plot_file))

    assert len(chapters) == 2

    # 第一章の検証
    ch1 = chapters[0]
    assert ch1["title"] == "第一章"
    assert ch1["name"] == "始まりの光"
    assert len(ch1["episodes"]) == 3

    ep1 = ch1["episodes"][0]
    assert ep1["title"] == "第一話"
    assert ep1["name"] == "旅立ち"
    assert ep1["content"] == ["これは旅立ちの本文です。", ""]

    ep2 = ch1["episodes"][1]
    assert ep2["title"] == "第二話"
    assert ep2["name"] == "出会い"
    assert ep2["content"] == [
        "旅の途中で新しい仲間に出会いました。",
        "ここも本文です。",
        "",
    ]

    ep3 = ch1["episodes"][2]
    assert ep3["title"] == "幕間一"
    assert ep3["name"] == "休息"
    assert ep3["content"] == ["戦いの合間の静かな時間。", ""]

    # 第2章の検証
    ch2 = chapters[1]
    assert ch2["title"] == "第2章"
    assert ch2["name"] == "新たな敵"
    assert len(ch2["episodes"]) == 1

    ep4 = ch2["episodes"][0]
    assert ep4["title"] == "第3話"
    assert ep4["name"] == "強襲"
    assert ep4["content"] == ["敵が突然現れた。"]


def test_parse_plot_duplicate_chapters(tmp_path):
    # 章が重複した際、名前が更新されるかのテスト
    plot_content = """
第一章：短い名前
第一話：話1
本文1

第一章：とても長い詳細な名前
第二話：話2
本文2
"""
    plot_file = tmp_path / "test_plot_duplicate.txt"
    plot_file.write_text(plot_content, encoding="utf-8")

    chapters = parse_plot(str(plot_file))

    # 章自体は重複排除されて1つのまま
    assert len(chapters) == 1
    assert chapters[0]["title"] == "第一章"
    # 名前の長さが長いほうに更新されていること
    assert chapters[0]["name"] == "とても長い詳細な名前"
    assert len(chapters[0]["episodes"]) == 2


def test_list_chapters(caplog):
    import logging

    chapters = [
        {
            "title": "第一章",
            "name": "章題1",
            "episodes": [
                {"title": "第一話", "name": "話題1", "content": []},
                {"title": "第二話", "name": "話題2", "content": []},
            ],
        }
    ]
    with caplog.at_level(logging.INFO):
        list_chapters(chapters)
    assert "1. 第一章: 章題1" in caplog.text
    assert "   - 第一話: 話題1" in caplog.text
    assert "   - 第二話: 話題2" in caplog.text


def test_get_chapter_episodes():
    chapters = [
        {
            "title": "第一章",
            "name": "章題1",
            "episodes": [{"title": "第一話", "name": "話題1", "content": []}],
        },
        {
            "title": "第二章",
            "name": "章題2",
            "episodes": [{"title": "第二話", "name": "話題2", "content": []}],
        },
    ]

    # 存在する章
    episodes = get_chapter_episodes(chapters, "第一章")
    assert episodes is not None
    assert len(episodes) == 1
    assert episodes[0]["title"] == "第一話"

    # 存在しない章
    episodes_none = get_chapter_episodes(chapters, "第三章")
    assert episodes_none is None
