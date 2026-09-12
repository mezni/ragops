from pathlib import Path
from types import SimpleNamespace

import pytest

from ingestion import RAGIndexingPipeline
from ingestion.sources import FileSystemSource
from tests.conftest import DATA_RAW


def _stub_embeddings(monkeypatch, dims: int = 8):
    """Routes every embedding call through a deterministic local stub,
    so integration tests run without network access or API cost."""

    def _fake(client, model, texts):
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[float(i % 7)] * dims)
                for i, _ in enumerate(list(texts))
            ]
        )

    monkeypatch.setattr("ingestion.pipeline.embedding_request", _fake)
    monkeypatch.setattr("ingestion.stages.embedder.embedding_request", _fake)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    _stub_embeddings(monkeypatch)
    return RAGIndexingPipeline(persist_dir=str(tmp_path / "chroma"))


def _write_doc(tmp_path: Path, name: str, body: str) -> Path:
    src = tmp_path / "billing"
    src.mkdir(exist_ok=True)
    f = src / name
    f.write_text(body, encoding="utf-8")
    return f


FULL_DOC = (
    "Document ID: AW-X-001\n"
    "Version: 3.0\n"
    "Status: Active\n"
    "\n"
    "Billing disputes must be investigated within five business days."
    "Customers may escalate unresolved cases to a senior billing specialist."
)


def test_full_pipeline_indexes_a_document(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)

    result = pipeline.run(f)

    assert result
    assert all(c.doc_id == "AW-X-001_rules" for c in result)
    assert pipeline.collection.count() == len(result)
    assert pipeline.stages["store"].get_document_hashes("AW-X-001_rules")


def test_full_pipeline_is_idempotent(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)

    first = pipeline.run(f)
    count_after_first = pipeline.collection.count()

    second = pipeline.run(f)

    assert second == []  # unchanged -> skipped
    assert pipeline.collection.count() == count_after_first
    assert len(first) == count_after_first


def test_modified_doc_is_versioned_not_purged(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    first = pipeline.run(f)
    assert pipeline.registry.get("AW-X-001_rules")["active_version"] == 0

    f.write_text(
        FULL_DOC.replace("five business days", "ten business days"),
        encoding="utf-8",
    )
    second = pipeline.run(f)

    assert second  # re-indexed as a new version
    record = pipeline.registry.get("AW-X-001_rules")
    assert record["active_version"] == 1
    # Old content is retired (inactive), not deleted -> count grows.
    assert pipeline.collection.count() == len(first) + len(second)

    tags = pipeline.stages["store"].get_document_versions("AW-X-001_rules")
    assert {t["version"]: t["is_active"] for t in tags} == {0: False, 1: True}


def test_search_excludes_old_version_after_change(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    pipeline.run(f)

    f.write_text(
        FULL_DOC.replace("five business days", "ten business days"),
        encoding="utf-8",
    )
    pipeline.run(f)

    hits = pipeline.search("investigation timeline?", top_k=5)
    metas = hits.get("metadatas", [[]])[0]
    assert metas
    # Bad/outdated (old-version) chunks never surface; only v1 is served.
    assert all(m.get("is_active") is True for m in metas)
    assert all(m.get("version") == 1 for m in metas)


def test_new_doc_starts_at_version_zero(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)

    result = pipeline.run(f)

    assert result
    assert all("_v0_chunk_" in c.chunk_id for c in result)
    assert all(c.metadata.version == 0 for c in result)
    record = pipeline.registry.get("AW-X-001_rules")
    assert record["active_version"] == 0
    assert record["is_active"] is True


def test_deleted_file_is_retired_as_inactive(pipeline, tmp_path):
    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    f = docs / "billing" / "gone.txt"
    f.write_text("This document is about to vanish.\n", encoding="utf-8")

    pipeline.ingest_source(FileSystemSource(docs))
    assert pipeline.registry.get("gone")["is_active"] is True

    f.unlink()
    results, failed = pipeline.ingest_source(FileSystemSource(docs))

    assert failed == []
    assert results == []  # nothing new was indexed
    record = pipeline.registry.get("gone")
    assert record["is_active"] is False
    tags = pipeline.stages["store"].get_document_versions("gone")
    assert all(t["is_active"] is False for t in tags)


def test_reappearing_file_reactivates_same_version(pipeline, tmp_path):
    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    f = docs / "billing" / "back.txt"
    body = "A policy that comes and goes.\n"
    f.write_text(body, encoding="utf-8")

    pipeline.ingest_source(FileSystemSource(docs))
    f.unlink()
    pipeline.ingest_source(FileSystemSource(docs))
    assert pipeline.registry.get("back")["is_active"] is False

    f.write_text(body, encoding="utf-8")
    results, failed = pipeline.ingest_source(FileSystemSource(docs))

    assert failed == []
    assert results == []  # re-activated, not re-embedded
    record = pipeline.registry.get("back")
    assert record["is_active"] is True
    assert record["active_version"] == 0
    tags = pipeline.stages["store"].get_document_versions("back")
    assert all(t["is_active"] for t in tags)


def test_rollback_restores_previous_version(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    pipeline.run(f)
    f.write_text(
        FULL_DOC.replace("five business days", "ten business days"),
        encoding="utf-8",
    )
    pipeline.run(f)
    assert pipeline.registry.get("AW-X-001_rules")["active_version"] == 1

    active = pipeline.rollback("AW-X-001_rules", version=0)

    assert active > 0
    record = pipeline.registry.get("AW-X-001_rules")
    assert record["active_version"] == 0
    tags = pipeline.stages["store"].get_document_versions("AW-X-001_rules")
    assert {t["version"]: t["is_active"] for t in tags} == {0: True, 1: False}

    hits = pipeline.search("investigation duration?", top_k=5)
    metas = hits.get("metadatas", [[]])[0]
    assert metas
    assert all(m.get("version") == 0 for m in metas)


def test_rollback_unknown_version_raises(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    pipeline.run(f)

    with pytest.raises(ValueError, match="cannot roll back"):
        pipeline.rollback("AW-X-001_rules", version=99)
    with pytest.raises(KeyError, match="No registry entry"):
        pipeline.rollback("unknown-doc", version=0)


def test_full_pipeline_repurges_when_content_changes(monkeypatch, tmp_path):
    # Backward-compat surface: old chunks are no longer active after a change.
    _stub_embeddings(monkeypatch)
    pipeline = RAGIndexingPipeline(persist_dir=str(tmp_path / "chroma"))
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    pipeline.run(f)
    old_hash = next(iter(pipeline.stages["store"].get_document_hashes("AW-X-001_rules")))

    f.write_text(FULL_DOC.replace("five business days", "ten business days"), encoding="utf-8")
    second = pipeline.run(f)

    assert second
    new_hash = pipeline.stages["store"].get_document_hashes("AW-X-001_rules")
    assert old_hash not in new_hash
    assert pipeline.collection.count() >= len(second)


def test_search_returns_stored_context(pipeline, tmp_path):
    f = _write_doc(tmp_path, "AW-X-001_rules.txt", FULL_DOC)
    pipeline.run(f)

    hits = pipeline.search("how long does a dispute investigation take?", top_k=3)

    ids = hits["ids"][0]
    assert ids
    assert all(i.startswith("AW-X-001_rules") for i in ids)
    assert len(hits["documents"][0]) == len(ids)


def test_run_batch_isolates_failures(pipeline, tmp_path):
    good = _write_doc(tmp_path, "good.txt", "This policy text is totally valid.\n")
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4\nthis is not a real pdf\n%%EOF")

    results, failed = pipeline.run_batch([bad, good])

    assert failed == [str(bad)]
    assert results  # the healthy file was still indexed
    assert pipeline.stages["store"].get_document_hashes("good")


def test_run_directory_indexes_all_matching_files(pipeline, tmp_path):
    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    (docs / "billing" / "a.txt").write_text("Alpha policy content.\n", encoding="utf-8")
    (docs / "billing" / "b.md").write_text("# Beta\nBeta policy content.\n", encoding="utf-8")

    results, failed = pipeline.run_directory(docs)

    assert not failed
    assert len(results) == 2
    assert pipeline.collection.count() == 2


def test_ingest_source_indexes_directory_tree_with_data_source(pipeline, tmp_path):
    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    (docs / "support").mkdir()
    (docs / "billing" / "a.txt").write_text("Alpha policy content.\n", encoding="utf-8")
    (docs / "billing" / "escalation").mkdir()
    (docs / "billing" / "escalation" / "b.md").write_text(
        "# Escalation\nEscalation policy.\n", encoding="utf-8"
    )
    (docs / "support" / "c.txt").write_text("Support FAQ text.\n", encoding="utf-8")

    results, failed = pipeline.ingest_source(FileSystemSource(docs))

    assert not failed
    assert len(results) == 3
    assert pipeline.collection.count() == 3

    refs_by_doc = {
        ref.doc_id: ref
        for ref in FileSystemSource(docs).discover()
    }
    for result in results:
        meta = result.metadata
        assert meta["data_source"] == "filesystem"
        assert meta["category"] == refs_by_doc[result.doc_id].category


def test_ingest_source_isolates_broken_file(pipeline, tmp_path):
    docs = tmp_path / "docs"
    (docs / "billing").mkdir(parents=True)
    good = docs / "billing" / "good.txt"
    good.write_text("Valid policy text.\n", encoding="utf-8")
    bad = docs / "billing" / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot a real pdf\n%%EOF")

    results, failed = pipeline.ingest_source(FileSystemSource(docs))

    assert failed == [str(bad)]
    assert results  # healthy file still indexed
    assert pipeline.collection.count() == len(results)


def test_real_pdf_pipeline_produces_markdown_tables(monkeypatch, tmp_path):
    _stub_embeddings(monkeypatch)
    pipeline = RAGIndexingPipeline(persist_dir=str(tmp_path / "chroma"))

    pdf = DATA_RAW / "billing" / "AW-BIL-001_billing_dispute_policy.pdf"
    result = pipeline.run(pdf)

    assert len(result) > 100
    assert any("| --- |" in c.text for c in result)


def test_pipeline_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        RAGIndexingPipeline()


def test_legacy_compat_imports():
    from ingestion import (
        ChunkerStage,
        EmbeddingStage,
        IngestionStage,
        VectorStoreStage,
    )
    from ingestion.stages import (
        Chunker,
        DocumentLoader,
        Embedder,
        VectorStore,
    )

    assert IngestionStage is DocumentLoader
    assert ChunkerStage is Chunker
    assert EmbeddingStage is Embedder
    assert VectorStoreStage is VectorStore