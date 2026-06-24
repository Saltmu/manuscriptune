from src.apply_findings import (
    apply_finding_to_text,
    extract_suggestion_candidate,
    parse_line_number,
)


def test_parse_line_number():
    assert parse_line_number("8行目") == 8
    assert parse_line_number("15") == 15
    assert parse_line_number(None) is None
    assert parse_line_number("行数不明") is None
    assert parse_line_number("第123行目") == 123


def test_extract_suggestion_candidate():
    assert (
        extract_suggestion_candidate("「こんにちは」に修正してください。")
        == "こんにちは"
    )
    assert (
        extract_suggestion_candidate("「二つの色」または「エネルギー」に変更。")
        == "エネルギー"
    )
    assert extract_suggestion_candidate("単なる説明文のみ") is None


def test_apply_finding_to_text_success_extracted():
    # Test case where LLM is disabled, and it extracts the replacement from the suggestion
    text_lines = [
        "昔々、あるところにおじいさんとおばあさんが住んでいました。\n",
        "おじいさんは山へしば刈りに行きました。\n",
        "おばあさんは川へ洗濯に行きました。\n",
    ]
    finding = {
        "id": "INT-001",
        "location": "2行目",
        "original": "しば刈り",
        "suggestion": "「芝刈り」に修正してください。",
    }

    # use_llm=False
    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is True
    assert applied_text == "芝刈り"
    assert method == "extracted"
    assert text_lines[1] == "おじいさんは山へ芝刈りに行きました。\n"


def test_apply_finding_to_text_not_found():
    text_lines = [
        "おじいさんは山へしば刈りに行きました。\n",
    ]
    finding = {
        "id": "INT-002",
        "location": "1",
        "original": "川へ洗濯",
        "suggestion": "「海へ釣り」に修正",
    }

    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is False
    assert "Could not find original text" in applied_text
    assert method is None


def test_apply_finding_to_text_no_candidate():
    text_lines = [
        "おじいさんは山へしば刈りに行きました。\n",
    ]
    finding = {
        "id": "INT-003",
        "location": "1",
        "original": "しば刈り",
        "suggestion": "漢字表記を修正してください。",  # No quotes
    }

    success, applied_text, method = apply_finding_to_text(
        text_lines, finding, model="test-model", use_llm=False
    )

    assert success is False
    assert "Could not extract replacement text" in applied_text
    assert method is None
