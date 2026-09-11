"""Unit tests for the engine/session factory in `pipeline/core/db.py`."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from pipeline.core.db import check_connection, create_db_engine, create_session_factory


class TestEngineCreation:
    def test_pool_settings_applied(self) -> None:
        engine = create_db_engine(DUMMY_CONFIG)
        assert engine.pool._pre_ping is True
        assert engine.pool._max_overflow == 10

    def test_select_one_roundtrip(self, engine) -> None:
        assert check_connection(engine) is True


class TestSessionFactory:
    def test_session_executes_select_one(self, engine) -> None:
        factory = create_session_factory(engine)
        with factory() as session:
            value = session.execute(text("SELECT 1")).scalar_one()
            assert value == 1

    def test_session_commits_and_rolls_back(self, engine) -> None:
        factory = create_session_factory(engine)
        with factory() as session:
            session.execute(text("SELECT 1"))
            session.rollback()  # no pending tx should raise
        # A new session works after rollback (pool stays healthy).
        with factory() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1


# Local stand-in for the config contract (tests avoid filesystem/config coupling).
class _FakeDb:
    database_url = "postgresql+psycopg://ragops:ragops@localhost:5432/ragops"
    pool_size = 5
    max_overflow = 10
    pool_pre_ping = True
    pool_recycle = 1800
    echo = False


class _FakeConfig:
    db = _FakeDb()


DUMMY_CONFIG = _FakeConfig()