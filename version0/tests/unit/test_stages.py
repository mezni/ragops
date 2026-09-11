from dataclasses import dataclass
from typing import Any, Dict

import pytest
from pypdf import PdfWriter

from indexing.stages import ChunkingStage, EmbeddingStage, IngestionStage
from indexing.stages.models import EmbeddedChunk, TextChunk
from loaders.base import RawPayload
from parsers.base import Document

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

@dataclass
class _FakePayloadModel:
    payload_id: str
    version: int


class FakeSession:
    def __init__(self):
        self.added: list = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


class FakeDatabaseManager:
    def __init__(self, statuses=None):
        self._statuses = list(statuses or ["CREATED"])
        self.calls: list = []
        self.session = FakeSession()
        self.last_active_ids = None

    def upsert_versioned_payload(self, payload):
        self.calls.append(payload)
        status = self._statuses.pop(0) if self._statuses else "CREATED"
        return _FakePayloadModel(payload.payload_id, 1), status

    def sync_deleted_payloads(self, active_source_ids):
        self.last_active_ids = active_source_ids
        return []

    def SessionLocal(self):
        return self.session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(db_manager=None):
    return {"db_manager": db_manager or FakeDatabaseManager()}


def make_payload(payload_id="doc-1", content_type="text/plain", metadata=None):
    return RawPayload(
        payload_id=payload_id,
        source_type="test",
        source_uri="s3://bucket/a.txt",
        raw_content="# Title\n\nsome content",
        content_type=content_type,
        metadata=metadata or {},
    )


# ===================================================================
# IngestionStage
# ===================================================================

class TestIngestionStage:
    def test_created_routes_to_text_parser(self):
        stage = IngestionStage()
        docs = stage.execute([make_payload()], _ctx())

        assert len(docs) == 1
        assert docs[0].payload_id == "doc-1"
        assert docs[0].payload_version == 1

    def test_updated_returns_document(self):
        stage = IngestionStage()
        docs = stage.execute([make_payload()], _ctx(FakeDatabaseManager(["UPDATED"])))

        assert len(docs) == 1

    def test_unchanged_skips_and_returns_empty_list(self):
        stage = IngestionStage()
        docs = stage.execute([make_payload()], _ctx(FakeDatabaseManager(["UNCHANGED"])))

        assert docs == []

    def test_routes_markdown_by_payload_extension(self):
        payload = make_payload(payload_id="readme.md")
        docs = IngestionStage().execute([payload], _ctx())

        assert docs[0].metadata["parser"] == "MarkdownParser"

    def test_pdf_content_type_routes_to_pdf_parser(self, tmp_path):
        pdf_path = tmp_path / "sample.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with pdf_path.open("wb") as fh:
            writer.write(fh)

        payload = make_payload(payload_id="report.pdf", content_type="application/pdf")
        payload.raw_content = str(pdf_path)

        docs = IngestionStage().execute([payload], _ctx())

        assert docs[0].metadata["parser"] == "PDFParser"

    def test_saves_document_records_via_session(self):
        db = FakeDatabaseManager(["CREATED"])
        IngestionStage().execute([make_payload()], _ctx(db))

        from core.database import DocumentModel
        assert len(db.session.added) == 1
        assert isinstance(db.session.added[0], DocumentModel)

    def test_passes_active_ids_to_sync_deleted(self):
        db = FakeDatabaseManager(["CREATED"])
        IngestionStage().execute([make_payload("a"), make_payload("b")], _ctx(db))

        assert db.last_active_ids == ["a", "b"]

    def test_empty_input_returns_empty(self):
        docs = IngestionStage().execute([], _ctx())
        assert docs == []


# ===================================================================
# ChunkingStage
# ===================================================================

def _doc(text="hello world", payload_id="doc-1", version=1):
    return Document(payload_id=payload_id, payload_version=version, cleaned_text=text)


class TestChunkingStage:
    def test_short_text_single_chunk(self):
        chunks = ChunkingStage(chunk_size=500, chunk_overlap=50).execute([_doc()], {})

        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].chunk_text == "hello world"

    def test_long_text_split_with_sliding_window(self):
        text = "a" * 1000
        chunks = ChunkingStage(chunk_size=300, chunk_overlap=50).execute([_doc(text)], {})

        assert len(chunks) == 4
        assert all(len(c.chunk_text) <= 300 for c in chunks)

    def test_chunk_ids_unique_and_prefixed(self):
        chunks = ChunkingStage(chunk_size=200, chunk_overlap=20).execute([_doc("x" * 600, version=2)], {})

        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        assert all(c.chunk_id.startswith("doc-1::v2::c") for c in chunks)

    def test_empty_doc_skipped(self):
        chunks = ChunkingStage().execute([_doc("")], {})
        assert chunks == []

    def test_metadata_carry_over(self):
        doc = Document(
            payload_id="doc-1",
            payload_version=1,
            cleaned_text="content",
            title="My Title",
            metadata={"custom": 1},
        )
        chunks = ChunkingStage().execute([doc], {})

        assert chunks[0].metadata["title"] == "My Title"
        assert chunks[0].metadata["custom"] == 1

    def test_multiple_documents_concatenated(self):
        d1 = _doc("aaa", payload_id="a", version=1)
        d2 = _doc("bbb", payload_id="b", version=1)
        chunks = ChunkingStage(chunk_size=2, chunk_overlap=0).execute([d1, d2], {})

        ids = {c.chunk_id for c in chunks}
        assert any("a::v1" in cid for cid in ids)
        assert any("b::v1" in cid for cid in ids)


# ===================================================================
# EmbeddingStage
# ===================================================================

class TestEmbeddingStage:
    def test_produces_1536_dim_vectors(self):
        chunks = ChunkingStage(chunk_size=200, chunk_overlap=20).execute([_doc("x" * 600)], {})
        embedded = EmbeddingStage().execute(chunks, {})

        assert len(embedded) == len(chunks)
        assert all(len(e.vector) == 1536 for e in embedded)

    def test_embedded_chunk_preserves_fields(self):
        chunks = ChunkingStage(chunk_size=200, chunk_overlap=20).execute(
            [_doc("content here", payload_id="doc-5", version=3)], {}
        )
        embedded = EmbeddingStage().execute(chunks, {})

        e = embedded[0]
        assert e.chunk_id == chunks[0].chunk_id
        assert e.payload_id == "doc-5"
        assert e.payload_version == 3

    def test_empty_input_returns_empty(self):
        assert EmbeddingStage().execute([], {}) == []

    def test_same_text_same_vector(self):
        doc = _doc("deterministic text")
        chunks = ChunkingStage(chunk_size=200).execute([doc, doc], {})
        embedded = EmbeddingStage().execute(chunks, {})

        assert embedded[0].vector == embedded[1].vector

    def test_different_text_different_vectors(self):
        c1 = TextChunk(chunk_id="1", payload_id="a", payload_version=1, chunk_index=0, chunk_text="cats")
        c2 = TextChunk(chunk_id="2", payload_id="b", payload_version=1, chunk_index=0, chunk_text="dogs")
        embedded = EmbeddingStage().execute([c1, c2], {})

        assert embedded[0].vector != embedded[1].vector


# ===================================================================
# GeneralizedPipeline (builder integration)
# ===================================================================

class TestPipelineIntegration:
    def test_build_and_run_pipeline(self, tmp_path):
        from indexing.builder import build_indexing_pipeline
        from core.database import DocumentModel

        (tmp_path / "hello.txt").write_text("hello world")

        pipeline = build_indexing_pipeline()

        assert pipeline.name == "VersionedIndexingPipeline"
        assert len(pipeline.stages) == 3
        assert [type(stage).__name__ for stage in pipeline.stages] == [
            "IngestionStage",
            "ChunkingStage",
            "EmbeddingStage",
        ]

        raw_payloads = [
            RawPayload(
                payload_id="hello.txt",
                source_type="filesystem",
                source_uri=f"file://{tmp_path}/hello.txt",
                raw_content="hello world",
                content_type="text/plain",
            )
        ]
        db = FakeDatabaseManager(["CREATED"])
        context = {"db_manager": db}

        embedded = pipeline.run(raw_payloads, context)

        assert len(embedded) > 0
        assert all(len(e.vector) == 1536 for e in embedded)
        assert isinstance(db.session.added[0], DocumentModel)
        assert db.last_active_ids == ["hello.txt"]