from pathlib import Path

import pytest

from loaders.filesystem import FilesystemLoader


def test_load_reads_directory_recursively(tmp_path):
    (tmp_path / "doc.md").write_text("# Title\n")
    (tmp_path / "notes.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("nested")

    payloads = FilesystemLoader(str(tmp_path)).load()

    assert len(payloads) == 3
    by_name = {Path(p.payload_id).name: p for p in payloads}

    assert by_name["doc.md"].content_type == "text/markdown"
    assert by_name["notes.txt"].content_type == "text/plain"
    assert by_name["notes.txt"].raw_content == "hello"
    assert by_name["notes.txt"].source_type == "filesystem"
    assert "deep.txt" in by_name


def test_non_recursive_ignores_subdirectories(tmp_path):
    (tmp_path / "top.txt").write_text("top")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_text("inner")

    payloads = FilesystemLoader(str(tmp_path), recursive=False).load()

    names = [Path(p.payload_id).name for p in payloads]
    assert names == ["top.txt"]


def test_extension_filter(tmp_path):
    (tmp_path / "data.csv").write_text("a,b")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "log.txt").write_text("log")

    payloads = FilesystemLoader(str(tmp_path), allowed_extensions={".csv"}).load()

    assert len(payloads) == 1
    assert payloads[0].content_type == "text/csv"


def test_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FilesystemLoader(str(tmp_path / "nope")).load()


def test_binary_file_stores_path_reference(tmp_path):
    pdf = tmp_path / "file.pdf"
    pdf.write_bytes(b"\x80\x81\x82\x83")

    payloads = FilesystemLoader(str(tmp_path), allowed_extensions={".pdf"}).load()

    assert len(payloads) == 1
    assert payloads[0].raw_content == str(pdf.resolve())
    assert payloads[0].metadata["file_hash"]


def test_metadata_includes_hash_and_size(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("abc")

    payloads = FilesystemLoader(str(tmp_path)).load()

    assert len(payloads) == 1
    meta = payloads[0].metadata
    assert "file_hash" in meta
    assert meta["file_size_bytes"] == 3
    assert meta["filename"] == "sample.txt"
    assert meta["file_extension"] == ".txt"