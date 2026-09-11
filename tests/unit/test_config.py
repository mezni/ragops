"""Unit tests for `PipelineConfig` (contracts/config-schema.md v1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.config import DbConfig, LogLevel, LoggingConfig, PipelineConfig

VALID_URL = "postgresql+psycopg://ragops:ragops@localhost:5432/ragops"
INVALID_URL = "postgresql://ragops:ragops@localhost:5432/ragops"  # missing +psycopg driver


def _db(**overrides) -> DbConfig:
    return DbConfig(database_url=VALID_URL, **overrides)


def _valid_init_kwargs() -> dict:
    return {"db": _db(), "logging": LoggingConfig()}


class TestDatabaseUrlValidation:
    def test_valid_url_accepted(self) -> None:
        assert _db().database_url == VALID_URL

    def test_invalid_dialect_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DbConfig(database_url=INVALID_URL)

    def test_url_is_required(self) -> None:
        with pytest.raises(ValidationError):
            DbConfig()


class TestPoolBounds:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"pool_size": 0},
            {"max_overflow": -1},
            {"pool_recycle": 59},
        ],
    )
    def test_out_of_bounds_rejected(self, overrides: dict) -> None:
        with pytest.raises(ValidationError):
            _db(**overrides)

    def test_defaults_match_contract(self) -> None:
        cfg = _db()
        assert cfg.pool_size == 5
        assert cfg.max_overflow == 10
        assert cfg.pool_pre_ping is True
        assert cfg.pool_recycle == 1800
        assert cfg.echo is False


class TestLoggingLevel:
    @pytest.mark.parametrize("level", list(LogLevel))
    def test_valid_levels_accepted(self, level: LogLevel) -> None:
        assert LoggingConfig(level=level).level == level

    def test_invalid_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoggingConfig(level="TRACE")

    def test_default_level_is_info(self) -> None:
        assert LoggingConfig().level == LogLevel.INFO


class TestUnknownKeys:
    def test_unknown_top_level_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineConfig(**_valid_init_kwargs(), whoops=1)


class TestEnvOverrides:
    def test_environment_overrides_yaml(self, monkeypatch) -> None:
        env_url = "postgresql+psycopg://override:override@localhost:5432/override"
        monkeypatch.setenv("DATABASE_URL", env_url)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        cfg = PipelineConfig()
        assert cfg.db.database_url == env_url
        assert cfg.logging.level == LogLevel.DEBUG

    def test_yaml_defaults_when_no_env(self, monkeypatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        cfg = PipelineConfig()
        assert cfg.db.database_url == VALID_URL
        assert cfg.logging.level == LogLevel.INFO