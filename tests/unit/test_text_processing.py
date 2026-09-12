from utils.text_processing import clean_text


def test_clean_text_strips_html_tags():
    raw = "<b>Bold</b> and <i>italic</i> text"
    assert clean_text(raw) == "Bold and italic text"


def test_clean_text_collapses_overlapping_tags():
    raw = "The <b>quick</b><b>brown</b> fox"
    assert clean_text(raw) == "The quick brown fox"


def test_clean_text_normalizes_newlines_and_spaces():
    raw = "line one\n\n\n   line two\t\tend\n"
    assert clean_text(raw) == "line one\n line two end"


def test_clean_text_returns_stripped():
    assert clean_text("   padded   ") == "padded"
    assert clean_text("") == ""