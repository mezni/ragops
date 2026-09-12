from pathlib import Path

import pytest

from ingestion.parsers import (
    DEFAULT_PARSERS,
    MarkdownParser,
    PDFParser,
    TextParser,
    get_parser,
    supported_extensions,
)
from tests.conftest import DATA_RAW


def test_get_parser_resolves_extensions_to_parsers(tmp_path):
    assert isinstance(get_parser(Path("doc.pdf")), PDFParser)
    assert isinstance(get_parser("doc.txt"), TextParser)
    assert isinstance(get_parser("doc.md"), MarkdownParser)
    assert isinstance(get_parser("doc.markdown"), MarkdownParser)


def test_get_parser_is_extension_based_not_existence_based(tmp_path):
    # The file need not exist — discovery happens on the path's extension.
    assert isinstance(get_parser("missing.pdf"), PDFParser)


def test_get_parser_unknown_extension_raises():
    with pytest.raises(ValueError, match="Unsupported file format"):
        get_parser("doc.csv")
    with pytest.raises(ValueError, match="Unsupported file format"):
        get_parser("doc.docx")


def test_supported_extensions_cover_pdf_text_markdown():
    extensions = supported_extensions()
    assert ".pdf" in extensions
    assert ".txt" in extensions
    assert ".md" in extensions
    assert ".markdown" in extensions


def test_default_parsers_all_document_parsers():
    assert all(parser.extensions for parser in DEFAULT_PARSERS)


def test_text_parser_reads_verbatim(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    assert TextParser().extract(f) == "hello\nworld\n"


def test_markdown_parser_reads_verbatim(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Heading\n\nBody **bold**.\n", encoding="utf-8")
    assert MarkdownParser().extract(f) == "# Heading\n\nBody **bold**.\n"


def test_pdf_parser_renders_tables_and_text():
    pdf = DATA_RAW / "billing" / "AW-BIL-001_billing_dispute_policy.pdf"
    raw = PDFParser().extract(pdf)

    assert raw
    assert "| --- |" in raw  # Markdown table grid
    assert "Billing Dispute Policy" in raw


def test_pdf_parser_reports_page_count():
    pdf = DATA_RAW / "billing" / "AW-BIL-001_billing_dispute_policy.pdf"
    assert PDFParser().page_count(pdf) == 19


def test_text_parser_page_count_is_none(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello\n", encoding="utf-8")
    assert TextParser().page_count(f) is None


def test_pdf_parser_page_count_none_for_missing_file(tmp_path):
    assert PDFParser().page_count(tmp_path / "missing.pdf") is None