from pathlib import Path

from parsers.text import TextParser
from parsers.markdown import MarkdownParser
from parsers.pdf import PDFParser


def test_text_parser_normalizes_and_infers_title():
    doc = TextParser().parse("  spaced  \n\n\nlines  \ntrailing  ", "p1", 1, {})
    assert doc.cleaned_text == "spaced\nlines\ntrailing"
    assert doc.title == "spaced"
    assert doc.payload_id == "p1"
    assert doc.payload_version == 1


def test_text_parser_long_first_line_falls_back_to_metadata_title():
    long_line = "x" * 200
    doc = TextParser().parse(f"{long_line}\nrest", "p1", 1, {"filename": "myfile.txt"})
    assert doc.title == "myfile.txt"


def test_text_parser_empty_content():
    doc = TextParser().parse("", "p1", 1, {})
    assert doc.cleaned_text == ""
    assert doc.title == "Untitled Document"


def test_markdown_parser_extracts_h1_title():
    doc = MarkdownParser().parse("# My Document\n\nSome body text.", "p1", 1, {})
    assert doc.title == "My Document"
    assert "Some body text." in doc.cleaned_text
    assert doc.metadata["parser"] == "MarkdownParser"


def test_markdown_parser_no_h1_falls_back_to_metadata():
    doc = MarkdownParser().parse("No heading here.", "p1", 1, {"filename": "readme.md"})
    assert doc.title == "readme.md"


def test_markdown_parser_removes_html_tags():
    doc = MarkdownParser().parse("<h1>Title</h1>\n\n<p>body</p>", "p1", 1, {})
    assert "<h1>" not in doc.cleaned_text
    assert "Title" in doc.cleaned_text
    assert "body" in doc.cleaned_text


def test_markdown_parser_squeezes_blank_lines():
    doc = MarkdownParser().parse("line one\n\n\n\n\nline two", "p1", 1, {})
    assert "\n\n\n" not in doc.cleaned_text
    assert "line one" in doc.cleaned_text
    assert "line two" in doc.cleaned_text


def test_pdf_parser_extracts_text(tmp_path):
    content = b"BT /F1 12 Tf 72 720 Td (Hello PDF world) Tj ET"
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
    )
    trailer = b"trailer << /Root 1 0 R >>\n"
    pdf = body + trailer + b"startxref\n" + str(len(body)).encode() + b"\n%%EOF\n"

    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(pdf)

    doc = PDFParser().parse(str(pdf_path), "p1", 1, {"filename": "test.pdf"})
    assert "Hello PDF world" in doc.cleaned_text
    assert doc.metadata["page_count"] == 1
    assert doc.metadata["parser"] == "PDFParser"


def test_pdf_parser_raises_on_missing_file():
    import pytest

    with pytest.raises(FileNotFoundError):
        PDFParser().parse("/nonexistent/fake.pdf", "p1", 1, {})