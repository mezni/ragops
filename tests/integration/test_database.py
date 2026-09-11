import pytest
from sqlalchemy import select, text

from core.database import RawPayloadModel
from loaders.base import RawPayload

pytestmark = pytest.mark.integration


def make_payload(payload_id, content, uri="s3://bucket/a.txt", content_type="text/plain"):
    return RawPayload(
        payload_id=payload_id,
        source_type="test",
        source_uri=uri,
        raw_content=content,
        content_type=content_type,
    )


def test_schema_columns_and_alembic(db):
    with db.engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version
        payload_id_uniqueness = connection.execute(
            text(
                "SELECT i.indisunique "
                "FROM pg_class t "
                "JOIN pg_index i ON i.indrelid = t.oid "
                "JOIN pg_class it ON it.oid = i.indexrelid "
                "WHERE t.relname = 'raw_payloads' "
                "AND it.relname = 'pk_raw_payloads_id_version'"
            )
        ).scalar_one()
        assert payload_id_uniqueness is True


def test_upsert_versioned_payload_creates_v1(db):
    payload, status = db.upsert_versioned_payload(make_payload("doc-1", "content v1"))

    assert status == "CREATED"
    assert payload.version == 1
    assert payload.is_active is True
    assert payload.is_deleted is False

    with db.SessionLocal() as session:
        row = session.execute(select(RawPayloadModel)).scalar_one()
        assert row.file_hash == db.compute_hash("content v1")


def test_upsert_versioned_payload_unchanged_keeps_version(db):
    db.upsert_versioned_payload(make_payload("doc-1", "content v1"))
    payload, status = db.upsert_versioned_payload(make_payload("doc-1", "content v1"))

    assert status == "UNCHANGED"
    assert payload.version == 1


def test_upsert_versioned_payload_updated_bumps_version_and_deactivates_old(db):
    db.upsert_versioned_payload(make_payload("doc-1", "content v1"))
    payload, status = db.upsert_versioned_payload(make_payload("doc-1", "content v2"))

    assert status == "UPDATED"
    assert payload.version == 2
    assert payload.is_active is True

    with db.SessionLocal() as session:
        versions = (
            session.execute(select(RawPayloadModel).order_by(RawPayloadModel.version))
            .scalars()
            .all()
        )
        assert [(v.version, v.is_active, v.file_hash) for v in versions] == [
            (1, False, db.compute_hash("content v1")),
            (2, True, db.compute_hash("content v2")),
        ]


def test_upsert_versioned_payload_restores_previous_content_as_new_version(db):
    db.upsert_versioned_payload(make_payload("doc-1", "content v1"))
    db.upsert_versioned_payload(make_payload("doc-1", "content v2"))
    payload, status = db.upsert_versioned_payload(make_payload("doc-1", "content v1"))

    assert status == "UPDATED"
    assert payload.version == 3


def test_sync_deleted_payloads(db):
    db.upsert_versioned_payload(make_payload("doc-1", "content v1"))
    db.upsert_versioned_payload(make_payload("doc-2", "content v1"))
    db.upsert_versioned_payload(make_payload("doc-3", "content v1"))

    deleted = db.sync_deleted_payloads(["doc-1", "doc-3"])

    assert sorted(deleted) == ["doc-2"]

    with db.SessionLocal() as session:
        rows = session.execute(select(RawPayloadModel)).scalars().all()
        state = {r.payload_id: (r.is_active, r.is_deleted) for r in rows}
        assert state["doc-1"] == (True, False)
        assert state["doc-2"] == (False, True)
        assert state["doc-3"] == (True, False)


def test_sync_deleted_payloads_flags_chunks_for_purge(db):
    from core.database import TextChunkModel

    payload_model, _ = db.upsert_versioned_payload(make_payload("doc-1", "content v1"))
    with db.SessionLocal() as session:
        payload_model = session.merge(payload_model)
        from core.database import DocumentModel

        doc = DocumentModel(
            payload_id=payload_model.payload_id,
            payload_version=payload_model.version,
            title="doc 1",
            cleaned_text="content v1",
        )
        session.add(doc)
        session.flush()
        session.add(
            TextChunkModel(
                chunk_id="chunk-1",
                document_id=doc.id,
                chunk_index=0,
                chunk_text="content v1",
            )
        )
        session.commit()

    db.sync_deleted_payloads([])

    with db.SessionLocal() as session:
        chunk = session.execute(select(TextChunkModel)).scalar_one()
        assert chunk.is_purged is True


def test_sync_deleted_with_no_stale_payloads(db):
    db.upsert_versioned_payload(make_payload("doc-1", "content v1"))

    assert db.sync_deleted_payloads(["doc-1"]) == []