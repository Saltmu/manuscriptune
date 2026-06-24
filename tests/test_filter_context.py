from src.filter_context import extract_keywords_from_novel


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
