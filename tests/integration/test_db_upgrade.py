"""Integration test: migration 0001 applies the `vector` extension, then `SELECT 1`.

Mirrors quickstart scenarios 4-6 and confirms the `pipeline db upgrade` CLI path
(`contracts/cli.md`) against a real docker postgres container.
"""

from __future__ import annotations

import sqlalchemy as sa
from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()


def test_db_upgrade_applies_vector_extension(engine) -> None:
    result = runner.invoke(app, ["db", "upgrade"])
    assert result.exit_code == 0, result.output

    with engine.connect() as conn:
        ext = conn.execute(
            sa.text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    assert ext == "vector"


def test_db_upgrade_is_idempotent(engine) -> None:
    first = runner.invoke(app, ["db", "upgrade"])
    second = runner.invoke(app, ["db", "upgrade"])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output


def test_healthcheck_returns_ok(engine) -> None:
    result = runner.invoke(app, ["healthcheck"])
    assert result.exit_code == 0, result.output
    assert '{"status":"ok"' in result.output


def test_select_one_roundtrip(engine) -> None:
    with engine.connect() as conn:
        value = conn.execute(sa.text("SELECT 1")).scalar_one()
    assert value == 1