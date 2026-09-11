import pytest
from sqlalchemy import select, text

from core.database import RawPayloadModel

pytestmark = pytest.mark.integration


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


def test_sync_payload_creates_v1(db):
    payload, status = db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")

    assert status == "CREATED"
    assert payload.version == 1
    assert payload.is_active is True
    assert payload.is_deleted is False

    with db.SessionLocal() as session:
        row = session.execute(select(RawPayloadModel)).scalar_one()
        assert row.file_hash == db.compute_hash("content v1")


def test_sync_payload_unchanged_keeps_version(db):
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")
    payload, status = db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")

    assert status == "UNCHANGED"
    assert payload.version == 1


def test_sync_payload_updated_bumps_version_and_deactivates_old(db):
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")
    payload, status = db.sync_payload("doc-1", "s3://bucket/a.txt", "content v2")

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


def test_sync_payload_restores_previous_content_as_new_version(db):
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v2")
    payload, status = db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")

    assert status == "UPDATED"
    assert payload.version == 3


def test_mark_deleted_missing_payloads(db):
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")
    db.sync_payload("doc-2", "s3://bucket/b.txt", "content v1")
    db.sync_payload("doc-3", "s3://bucket/c.txt", "content v1")

    deleted = db.mark_deleted_missing_payloads(["doc-1", "doc-3"])

    assert sorted(deleted) == ["doc-2"]

    with db.SessionLocal() as session:
        rows = session.execute(select(RawPayloadModel)).scalars().all()
        state = {r.payload_id: (r.is_active, r.is_deleted) for r in rows}
        assert state["doc-1"] == (True, False)
        assert state["doc-2"] == (False, True)
        assert state["doc-3"] == (True, False)


def test_mark_deleted_with_no_stale_payloads(db):
    db.sync_payload("doc-1", "s3://bucket/a.txt", "content v1")

    assert db.mark_deleted_missing_payloads(["doc-1"]) == []