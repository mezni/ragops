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
    assert doc.metadata.category == "billing"
    assert doc.metadata.file_type == ".txt"
    assert doc.metadata.doc_version == "1.2"
    assert doc.metadata.content_hash
    assert doc.metadata.department == "Engineering"
    assert doc.metadata.status == "Active"
    assert doc.metadata.data_source == "filesystem"
    assert "Some actual policy body text." in doc.content


def test_run_markdown_constructs_document(billing_dir):
    f = billing_dir / "AW-X-002_runbook.md"
    f.write_text(FRONTMATTER + "\n# Runbook\nSection body content.\n", encoding="utf-8")

    doc = DocumentLoader().run(f)

    assert doc.doc_id == "AW-X-002_runbook"
    assert doc.metadata.file_type == ".md"
    assert doc.metadata.category == "billing"
    assert "# Runbook" in doc.content


def test_run_markdown_raw_assert_parses_via_parsers(billing_dir):
    # .md/.markdown both map to the MarkdownParser via the registry.
    from ingestion.parsers import get_parser

    f = billing_dir / "note.markdown"
    f.write_text(FRONTMATTER + "\nbody\n", encoding="utf-8")
    assert get_parser(f).extensions == (".md", ".markdown")

    doc = DocumentLoader().run(f)
    assert doc.metadata.file_type == ".markdown"


def test_run_pdf_extracts_markdown_tables():
    pdf = DATA_RAW / "billing" / "AW-BIL-001_billing_dispute_policy.pdf"
    doc = DocumentLoader().run(pdf)

    assert doc.content
    assert doc.doc_id == "AW-BIL-001_billing_dispute_policy"
    assert doc.metadata.category == "billing"
    assert doc.metadata.content_hash
    assert doc.metadata.total_pages >= 1  # pdfplumber reports the page count
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


def test_document_gets_governance_defaults_from_config(billing_dir):
    # No frontmatter overrides -> centralized ragops.toml defaults fill in.
    f = billing_dir / "plain.txt"
    f.write_text("Just some content, no header block.\n", encoding="utf-8")

    md = DocumentLoader().run(f).metadata

    assert md.tenant_id == "default_tenant"
    assert md.access_roles == ["public"]
    assert md.classification == "internal"
    assert md.doc_type == "document"
    assert md.language == "en"
    assert md.status == "active"
    assert md.doc_version == "1.0"
    assert md.effective_date is None
    assert md.title is None
    assert md.author is None


def test_frontmatter_overrides_governance_defaults(billing_dir):
    header = (
        "Doc Type: policy\n"
        "Classification: confidential\n"
        "Tenant ID: acme-01\n"
        "Title: Acceptable Use Policy\n"
        "Author: Alice\n"
        "Effective Date: 2026-03-01\n"
    )
    f = billing_dir / "aup.txt"
    f.write_text(header + "\nBody.\n", encoding="utf-8")

    md = DocumentLoader().run(f).metadata

    assert md.doc_type == "policy"
    assert md.classification == "confidential"
    assert md.tenant_id == "acme-01"
    assert md.title == "Acceptable Use Policy"
    assert md.author == "Alice"
    assert md.effective_date == "2026-03-01"
    assert "Title: Acceptable Use Policy" not in md.source_path  # stripped

    # Untouched keys still fall back to the centralized defaults.
    assert md.language == "en"
    assert md.status == "active"


def test_department_falls_back_to_category(billing_dir):
    # No "Department:" line -> the folder name (category) is used.
    nested = billing_dir / "escalation"
    nested.mkdir()
    f = nested / "escalation_policy.txt"
    f.write_text("Body only.\n", encoding="utf-8")

    md = DocumentLoader().run(f).metadata

    assert md.department == "escalation"
    assert md.category == "escalation"


def test_markdown_file_has_no_page_count(billing_dir):
    f = billing_dir / "note.md"
    f.write_text("note\n", encoding="utf-8")

    md = DocumentLoader().run(f).metadata
    assert md.total_pages is None