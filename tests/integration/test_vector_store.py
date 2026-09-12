from ingestion.schemas import EmbeddedChunk
from ingestion.stages.vector_store import VectorStore


def _mk_chunks(n: int = 5, dims: int = 8, doc_id: str = "d"):
    return [
        EmbeddedChunk(
            chunk_id=f"{doc_id}_c{i}",
            doc_id=doc_id,
            text=f"Some knowledge text number {i}",
            embedding=[float(i)] * dims,
            metadata={},
        )
        for i in range(n)
    ]


def test_upsert_and_query(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert(_mk_chunks())

    assert store.count == 5

    hits = store.query([1.0] * 8, top_k=2)
    ids = hits["ids"][0]
    assert len(ids) == 2
    assert all(i.startswith("d_c") for i in ids)


def test_upsert_empty_is_noop(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    assert store.upsert([]) == 0
    assert store.count == 0


def test_get_document_hashes_groups_by_doc(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    chunks = _mk_chunks()
    for c in chunks:
        c.metadata["content_hash"] = "abc123"
    store.upsert(chunks)

    assert store.get_document_hashes("d") == {"abc123"}
    assert store.get_document_hashes("other") == set()


def test_delete_document_removes_only_that_doc(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert(_mk_chunks(doc_id="keep"))
    store.upsert(_mk_chunks(doc_id="drop"))

    assert store.delete_document("drop") == 5
    assert store.count == 5
    assert store.get_document_hashes("drop") == set()


def test_upsert_stamps_version_and_active_tags(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert(_mk_chunks(), version=3, is_active=True)

    result = store.collection.get(
        where={"doc_id": "d"},
        include=["metadatas"],
    )
    metas = result["metadatas"]
    assert all(m["version"] == 3 for m in metas)
    assert all(m["is_active"] is True for m in metas)


def _mk_version_chunks(prefix: str, n: int = 4, dims: int = 8):
    return [
        EmbeddedChunk(
            chunk_id=f"{prefix}_c{i}",
            doc_id="d",
            text=f"Version content {i}",
            embedding=[float(i)] * dims,
            metadata={},
        )
        for i in range(n)
    ]


def test_deactivate_then_activate_version(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    store.upsert(_mk_version_chunks("d_v0"), version=0, is_active=True)
    store.upsert(_mk_version_chunks("d_v1"), version=1, is_active=True)

    # A content change retires the old version's chunks (kept, not deleted).
    assert store.deactivate_document("d") == 8
    assert store.activate_version("d", version=1) == 4

    tags = store.get_document_versions("d")
    assert {t["version"]: t["is_active"] for t in tags} == {0: False, 1: True}

    # Roll back: v0 re-activated, v1 retired.
    store.activate_version("d", version=0)
    tags = store.get_document_versions("d")
    assert {t["version"]: t["is_active"] for t in tags} == {0: True, 1: False}