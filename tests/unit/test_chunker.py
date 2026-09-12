import pytest

from ingestion.schemas import Document, DocumentMetadata
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
        assert nxt.metadata.char_start < prev.metadata.char_end
        assert nxt.metadata.char_start > prev.metadata.char_start
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


def test_chunks_inherit_document_metadata(sample_doc):
    doc = sample_doc.model_copy(
        update={
            "metadata": DocumentMetadata(
                doc_id="doc1",
                source_path="billing/doc1.txt",
                tenant_id="acme-01",
                access_roles=["billing_admin"],
                classification="confidential",
                department="billing",
                doc_type="policy",
                status="active",
            )
        }
    )
    chunks = Chunker(chunk_size=500).run(doc)

    assert all(c.metadata.tenant_id == "acme-01" for c in chunks)
    assert all(c.metadata.classification == "confidential" for c in chunks)
    assert all(c.metadata.department == "billing" for c in chunks)
    assert all(c.metadata.doc_type == "policy" for c in chunks)
    assert all(c.metadata.status == "active" for c in chunks)


def test_chunks_carry_total_chunks_and_index(sample_doc):
    chunks = Chunker(chunk_size=500, chunk_overlap=50).run(sample_doc)

    assert len(chunks) > 1
    assert {c.metadata.total_chunks for c in chunks} == {len(chunks)}
    assert [c.metadata.chunk_index for c in chunks] == list(range(len(chunks)))


def test_each_chunk_has_its_own_content_hash_and_timestamps(sample_doc):
    chunks = Chunker(chunk_size=500, chunk_overlap=50).run(sample_doc)

    assert len(chunks) > 1
    assert len({c.metadata.content_hash for c in chunks}) == len(chunks)
    assert all(len(c.metadata.content_hash) == 64 for c in chunks)
    assert all(c.metadata.last_updated for c in chunks)
    assert all(not c.metadata.is_active is False for c in chunks)


def test_chunk_breadcrumb_recovers_section_hierarchy():
    doc = Document(
        doc_id="d",
        content=(
            "# Billing Policy\n"
            "Billing disputes are handled by Finance.\n"
            "## Refunds\n"
            "Refund requests take ten days.\n"
            "### Exceptions\n"
            "Exceptions require manager approval.\n"
        ),
        source="billing/policy.txt",
        metadata=DocumentMetadata(doc_id="d", source_path="billing/policy.txt"),
    )

    chunks = Chunker(chunk_size=200).run(doc)

    assert chunks
    # The leaf chunk (Exceptions) carries the full breadcrumb.
    leaf = max(chunks, key=lambda c: c.chunk_index)
    assert "Billing Policy > Refunds > Exceptions" in leaf.metadata.header_path
    # Earlier chunks capture only the section relevant at their offset.
    first = min(chunks, key=lambda c: c.chunk_index)
    assert "Billing Policy" in first.metadata.header_path


def test_chunk_breadcrumb_supports_numbered_sections():
    doc = Document(
        doc_id="d",
        content="1. Overview\nSetup steps for the pipeline.\n2. Troubleshooting\nCommon issues and fixes.\n",
        source="ops.txt",
    )
    chunks = Chunker(chunk_size=200).run(doc)

    second = max(chunks, key=lambda c: c.chunk_index)
    assert "2 Troubleshooting" in second.metadata.header_path