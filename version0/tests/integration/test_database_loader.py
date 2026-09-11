import pytest
from sqlalchemy import text

from loaders.database import DatabaseLoader
from core.config import settings

pytestmark = pytest.mark.integration


@pytest.fixture()
def seed_payloads(db):
    with db.engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_payloads "
                "(payload_id, version, file_hash, source_uri, raw_content, content_type, "
                "is_active, is_deleted, created_at, updated_at) "
                "VALUES "
                "('doc-1', 1, 'abc', 's3://a.txt', 'content v1', 'text/plain', true, false, now(), now()), "
                "('doc-1', 2, 'def', 's3://a.txt', 'content v2', 'text/plain', true, false, now(), now()), "
                "('doc-2', 1, 'ghi', 's3://b.txt', 'content b', 'text/plain', true, false, now(), now()), "
                "('doc-3', 1, 'jkl', 's3://c.txt', 'deleted', 'text/plain', false, true, now(), now())"
            )
        )
        conn.commit()
    yield


def test_loads_all_active_non_deleted_rows(seed_payloads):
    loader = DatabaseLoader(
        connection_url=settings.DATABASE_URL,
        query="SELECT * FROM raw_payloads WHERE is_active = true AND is_deleted = false",
        id_column="payload_id",
        content_column="raw_content",
    )

    payloads = loader.load()

    prefixed_ids = sorted(p.payload_id for p in payloads)
    assert prefixed_ids == ["relational_db::doc-1", "relational_db::doc-1", "relational_db::doc-2"]
    assert all(p.source_type == "database" for p in payloads)


def test_id_and_content_column_mapping(seed_payloads):
    loader = DatabaseLoader(
        connection_url=settings.DATABASE_URL,
        query="SELECT payload_id, raw_content, file_hash FROM raw_payloads WHERE payload_id = 'doc-2' AND is_active = true",
        id_column="payload_id",
        content_column="raw_content",
    )

    payloads = loader.load()
    assert len(payloads) == 1
    assert payloads[0].payload_id == "relational_db::doc-2"
    assert payloads[0].raw_content == "content b"
    assert "raw_row" in payloads[0].metadata


def test_skips_empty_id_or_content():
    loader = DatabaseLoader(
        connection_url=settings.DATABASE_URL,
        query="SELECT 1 AS id, '' AS content",
        id_column="id",
        content_column="content",
    )
    payloads = loader.load()
    assert payloads == []
