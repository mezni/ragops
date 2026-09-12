from types import SimpleNamespace

import pytest

from ingestion import cli
from ingestion.sources import FileSystemSource


def test_default_input_dir_is_data_raw():
    args = cli.build_parser().parse_args([])
    assert args.input_dir == "data/raw"
    assert args.query
    assert args.top_k == 3
    assert args.no_search is False


def test_custom_flags_parse():
    args = cli.build_parser().parse_args(
        ["/some/dir", "--query", "escalation?", "--top-k", "5",
         "--patterns", "*.pdf", "*.md", "--no-search"]
    )
    assert args.input_dir == "/some/dir"
    assert args.query == "escalation?"
    assert args.top_k == 5
    assert args.patterns == ["*.pdf", "*.md"]
    assert args.no_search is True


def test_cli_returns_nonzero_for_missing_input_dir():
    rc = cli.main(["/path/that/does/not/exist"])
    assert rc != 0


def _stub_embeddings(monkeypatch):
    def _fake(client, model, texts):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * 8) for _ in list(texts)]
        )

    monkeypatch.setattr("ingestion.pipeline.embedding_request", _fake)
    monkeypatch.setattr("ingestion.stages.embedder.embedding_request", _fake)


def test_cli_scans_directory_and_searches(monkeypatch, tmp_path):
    _stub_embeddings(monkeypatch)

    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    (docs / "billing" / "a.txt").write_text(
        "Billing disputes escalate to a senior specialist.\n", encoding="utf-8"
    )

    store = tmp_path / "chroma"
    rc = cli.main(
        [str(docs), "--query", "billing escalation", "--top-k", "2",
         "--persist-dir", str(store)]
    )
    assert rc == 0


def test_cli_skips_search_when_collection_empty(monkeypatch, tmp_path):
    # Empty input dir against a fresh store: no crash, returns 0.
    empty = tmp_path / "empty"
    empty.mkdir()
    store = tmp_path / "chroma"
    rc = cli.main([str(empty), "--no-search", "--persist-dir", str(store)])
    assert rc == 0


def test_filesystem_source_missing_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Input directory not found"):
        FileSystemSource(tmp_path / "nope").discover()