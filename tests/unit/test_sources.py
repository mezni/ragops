from pathlib import Path

import pytest

from ingestion.sources import DocumentSource, FileSystemSource


@pytest.fixture
def docs_tree(tmp_path) -> Path:
    (tmp_path / "billing").mkdir()
    (tmp_path / "billing" / "escalation").mkdir()
    (tmp_path / "support").mkdir()

    (tmp_path / "billing" / "AW-BIL-001_billing_rules.txt").write_text(
        "billing rule", encoding="utf-8"
    )
    (tmp_path / "billing" / "escalation" / "AW-ESC-001_escalation.pdf").write_bytes(
        b"%PDF-1.4 fake"
    )
    (tmp_path / "support" / "AW-SUP-001_faq.md").write_text(
        "# FAQ", encoding="utf-8"
    )
    (tmp_path / "billing" / "notes.csv").write_text("a,b\n", encoding="utf-8")
    (tmp_path / "root.txt").write_text("root file", encoding="utf-8")
    return tmp_path


def test_filesystem_source_discover_scans_recursively(docs_tree):
    refs = FileSystemSource(docs_tree).discover()

    locators = {ref.locator for ref in refs}
    assert locators == {
        str(docs_tree / "billing" / "AW-BIL-001_billing_rules.txt"),
        str(docs_tree / "billing" / "escalation" / "AW-ESC-001_escalation.pdf"),
        str(docs_tree / "support" / "AW-SUP-001_faq.md"),
        str(docs_tree / "root.txt"),
    }


def test_filesystem_source_restricts_by_pattern(docs_tree):
    refs = FileSystemSource(docs_tree, patterns=("*.txt",)).discover()
    assert {Path(ref.locator).suffix for ref in refs} == {".txt"}
    assert len(refs) == 2  # billing/txt + root.txt


def test_filesystem_source_reference_metadata(docs_tree):
    refs = FileSystemSource(docs_tree).discover()
    by_name = {ref.file_name: ref for ref in refs}

    billing = by_name["AW-BIL-001_billing_rules.txt"]
    assert billing.doc_id == "AW-BIL-001_billing_rules"
    assert billing.category == "billing"
    assert billing.file_type == ".txt"
    assert billing.data_source == "filesystem"
    assert Path(billing.locator).is_file()

    root_file = by_name["root.txt"]
    assert root_file.category == docs_tree.name  # top-level file -> folder name


def test_filesystem_source_no_matches_returns_empty(tmp_path):
    assert FileSystemSource(tmp_path).discover() == []


def test_filesystem_source_is_a_document_source():
    assert issubclass(FileSystemSource, DocumentSource)
    assert FileSystemSource.source_type == "filesystem"