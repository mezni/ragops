from pathlib import Path

import pytest

from ingestion.stages.loader import DocumentLoader
from tests.conftest import DATA_RAW

FRONTMATTER = (
    "Document ID: AW-X-001\n"
    "Version: 1.2\n"
    "Department: Engineering\n"
    "Last Updated: 2026-01-15\n"
    "Status: Active\n"
)
BODY = "\nSome actual policy body text.\n"


@pytest.fixture
def billing_dir(tmp_path) -> Path:
    d = tmp_path / "billing"
    d.mkdir()
    return d


def test_extract_frontmatter_parses_metadata():
    body, meta = DocumentLoader.extract_frontmatter(FRONTMATTER + BODY)
    assert meta["document_id"] == "AW-X-001"
    assert meta["doc_version"] == "1.2"
    assert meta["department"] == "Engineering"
    assert meta["last_updated"] == "2026-01-15"
    assert meta["status"] == "Active"
    assert "Document ID" not in body
    assert "Some actual policy body text." in body


def test_run_txt_constructs_document(billing_dir):
    f = billing_dir / "AW-X-001_policy.txt"
    f.write_text(FRONTMATTER + BODY, encoding="utf-8")

    doc = DocumentLoader().run(f)

    assert doc.doc_id == "AW-X-001_policy"
    assert doc.metadata["category"] == "billing"
    assert doc.metadata["file_type"] == ".txt"
    assert doc.metadata["doc_version"] == "1.2"
    assert doc.metadata["content_hash"]
    assert "Some actual policy body text." in doc.content


def test_run_markdown_constructs_document(billing_dir):
    f = billing_dir / "AW-X-002_runbook.md"
    f.write_text(FRONTMATTER + "\n# Runbook\nSection body content.\n", encoding="utf-8")

    doc = DocumentLoader().run(f)

    assert doc.doc_id == "AW-X-002_runbook"
    assert doc.metadata["file_type"] == ".md"
    assert doc.metadata["category"] == "billing"
    assert "# Runbook" in doc.content


def test_run_markdown_raw_assert_parses_via_parsers(billing_dir):
    # .md/.markdown both map to the MarkdownParser via the registry.
    from ingestion.parsers import get_parser

    f = billing_dir / "note.markdown"
    f.write_text(FRONTMATTER + "\nbody\n", encoding="utf-8")
    assert get_parser(f).extensions == (".md", ".markdown")

    doc = DocumentLoader().run(f)
    assert doc.metadata["file_type"] == ".markdown"


def test_run_pdf_extracts_markdown_tables():
    pdf = DATA_RAW / "billing" / "AW-BIL-001_billing_dispute_policy.pdf"
    doc = DocumentLoader().run(pdf)

    assert doc.content
    assert doc.doc_id == "AW-BIL-001_billing_dispute_policy"
    assert doc.metadata["category"] == "billing"
    assert doc.metadata["content_hash"]
    assert "| --- |" in doc.content  # tables rendered as Markdown grids


def test_run_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        DocumentLoader().run(tmp_path / "nope.pdf")


def test_run_unsupported_format_raises(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        DocumentLoader().run(f)


def test_run_empty_document_raises(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        DocumentLoader().run(f)