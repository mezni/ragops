"""Database engine, connection pool, and session factory.

DB access must flow through this module only — never ad-hoc connections
(plan.md constraints / contracts/config-schema.md).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from pipeline.config import PipelineConfig


def create_db_engine(config: PipelineConfig) -> Engine:
    """Create a SQLAlchemy engine from validated `PipelineConfig`."""
    return create_engine(
        config.db.database_url,
        pool_size=config.db.pool_size,
        max_overflow=config.db.max_overflow,
        pool_pre_ping=config.db.pool_pre_ping,
        pool_recycle=config.db.pool_recycle,
        echo=config.db.echo,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a scoped session factory bound to `engine`."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)


def check_connection(engine: Engine) -> bool:
    """Execute ``SELECT 1`` through the engine.

    Used by the healthcheck; raises on connection failure.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True