import os
import unittest.mock

from src import filter_context
from src.filter_context import (
    extract_keywords_from_novel,
    is_basic_context_file,
    split_into_sections,
)


def test_extract_keywords_from_novel():
    # Katakana words (length >= 2) and Kanji words (length >= 2) should be extracted.
    # Stopwords should be filtered out.
    text = "アルフは言った。このことは重要だが、彼にとっては普通の出来事だった。調律師としての自覚。"

    keywords = extract_keywords_from_novel(text)

    # Katakana
    assert "アルフ" in keywords

    # Kanji
    assert "重要" not in keywords
    assert "調律師" in keywords
    assert "自覚" in keywords

    # Stopwords (filtered out)
    assert "こと" not in keywords
    assert "普通" not in keywords


def test_extract_keywords_from_novel_stopwords():
    # Let's test specific stopwords filtering
    text = "意識と感覚と存在について、普通の方法で解決した。"
    keywords = extract_keywords_from_novel(text)

    # These are all in STOPWORDS, so they should not be extracted
    assert "意識" not in keywords
    assert "感覚" not in keywords
    assert "存在" not in keywords
    assert "普通" not in keywords
    assert "方法" not in keywords
    assert "解決" not in keywords


def test_extract_keywords_from_novel_short_words():
    # Single character Kanji or Katakana should not be extracted
    text = "木と川と山。アとイ。"
    keywords = extract_keywords_from_novel(text)

    assert "木" not in keywords
    assert "川" not in keywords
    assert "山" not in keywords
    assert "ア" not in keywords
    assert "イ" not in keywords


def test_is_basic_context_file():
    # Test filenames containing priority keywords
    assert is_basic_context_file("02_創世記から現代まで_年表.txt") is True
    assert is_basic_context_file("歴史設定.txt") is True
    assert is_basic_context_file("magic_system_rule.txt") is True
    assert is_basic_context_file("物理法則.txt") is True

    # Test filenames that should not match
    assert is_basic_context_file("character_profile_ミーナ.txt") is False
    assert is_basic_context_file("01_用語集.txt") is False


def test_split_into_sections_markdown():
    content = """# Title
This is title section.

## Subtitle
This is subtitle section.
Still inside subtitle.

■ Block Header
Japanese marker section.
"""
    sections = split_into_sections(content)
    assert len(sections) == 3
    assert sections[0].startswith("# Title")
    assert "This is title section." in sections[0]
    assert sections[1].startswith("## Subtitle")
    assert sections[2].startswith("■ Block Header")


def test_split_into_sections_fallback():
    content = """Paragraph 1.

Paragraph 2.

Paragraph 3."""
    sections = split_into_sections(content)
    assert len(sections) == 3
    assert sections[0] == "Paragraph 1."
    assert sections[1] == "Paragraph 2."
    assert sections[2] == "Paragraph 3."


def test_split_into_sections_pre_content():
    content = """Intro text here.
More intro.

# Header 1
Content 1.
"""
    sections = split_into_sections(content)
    assert len(sections) == 2
    assert sections[0] == "Intro text here.\nMore intro."
    assert sections[1].startswith("# Header 1")


def test_filter_context_main_integration(tmp_path):
    # Create dummy directories
    sources_dir = tmp_path / "data" / "sources"
    sources_dir.mkdir(parents=True)

    # 1. Create a basic context file (timeline)
    timeline_content = """■ 創世記
神が世界を創った。

■ 第一紀
調律師が現れた。
"""
    timeline_file = sources_dir / "02_歴史年表.txt"
    timeline_file.write_text(timeline_content, encoding="utf-8")

    # 2. Create a standard setting file (will be chunked into sections)
    settings_content = """# 物理法則
世界はエネルギーで満ちている。

# 魔力体系
魔法は調律師によってのみ使える。
"""
    settings_file = sources_dir / "physics.txt"
    settings_file.write_text(settings_content, encoding="utf-8")

    # 3. Create dummy novel draft
    novel_content = "アルフは調律師として、魔法を使った。エネルギーを感じる。"
    novel_file = tmp_path / "novel.txt"
    novel_file.write_text(novel_content, encoding="utf-8")

    output_file = tmp_path / "filtered_context.txt"

    # Patch the sources_dir and sys.argv, then run main
    with unittest.mock.patch(
        "sys.argv", ["filter_context.py", str(novel_file), str(output_file)]
    ):
        original_join = os.path.join

        def mock_join(*args):
            # If the join points to .../data/sources, redirect to tmp_path/data/sources
            joined = original_join(*args)
            if joined.replace("\\", "/").endswith("data/sources"):
                return str(sources_dir)
            return joined

        with unittest.mock.patch("os.path.join", side_effect=mock_join):
            filter_context.main()

    # Verify the output
    assert output_file.exists()
    output_text = output_file.read_text(encoding="utf-8")

    # Basic context must be prioritized, unfragmented and keep its order
    assert "=== BASIC CONTEXTS (PRIORITIZED & UNFRAGMENTED) ===" in output_text
    assert "02_歴史年表.txt" in output_text
    assert "■ 創世記\n神が世界を創った。\n\n■ 第一紀\n調律師が現れた。" in output_text

    # Standard settings should be chunked and matched
    assert (
        "physics.txt (Section 1" in output_text
    )  # "# 魔力体系..." has "調律師" which matches novel
    assert "魔法は調律師によってのみ使える。" in output_text
