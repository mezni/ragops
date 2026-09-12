import pytest

from ingestion.schemas import Document
from ingestion.stages.chunker import Chunker


@pytest.fixture
def sample_doc() -> Document:
    return Document(
        doc_id="doc1",
        content="Hello world. " * 200,
        source="billing/doc1.txt",
    )


def test_chunker_single_short_document_is_one_chunk():
    doc = Document(doc_id="d", content="Just a short policy note.", source="x")
    chunks = Chunker().run(doc)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "d_chunk_0"
    assert chunks[0].doc_id == "d"
    assert chunks[0].text == "Just a short policy note."


def test_chunker_respects_chunk_size(sample_doc):
    chunks = Chunker(chunk_size=500, chunk_overlap=50).run(sample_doc)
    assert chunks
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(c.text.strip() for c in chunks)


def test_chunker_consecutive_chunks_overlap(sample_doc):
    chunks = Chunker(chunk_size=500, chunk_overlap=50).run(sample_doc)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.metadata["char_start"] < prev.metadata["char_end"]
        assert nxt.metadata["char_start"] > prev.metadata["char_start"]
        assert nxt.chunk_index == prev.chunk_index + 1


def test_chunker_oversized_pure_character_block_stays_under_limit():
    doc = Document(doc_id="d", content="A" * 10_000, source="x")
    chunks = Chunker(chunk_size=500, chunk_overlap=50).run(doc)

    assert len(chunks) > 10
    assert chunks[0].text == "A" * 500
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(c.text for c in chunks)


def test_chunker_validation_errors():
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        Chunker(chunk_size=0)
    with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
        Chunker(chunk_overlap=-1)
    with pytest.raises(ValueError, match="must be < chunk_size"):
        Chunker(chunk_size=100, chunk_overlap=100)