from core.config import Environment, Settings
import pytest
from pydantic import ValidationError


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.ENV == Environment.DEVELOPMENT
    assert settings.LOG_LEVEL == "INFO"
    assert settings.JSON_LOGS is True
    assert settings.DATABASE_URL.startswith("postgresql://")
    assert settings.VECTOR_STORE_PROVIDER == "qdrant"
    assert settings.CHUNK_SIZE == 500
    assert settings.CHUNK_OVERLAP == 50


def test_environment_override(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("JSON_LOGS", "false")
    monkeypatch.setenv("CHUNK_SIZE", "1000")

    settings = Settings(_env_file=None)

    assert settings.ENV == Environment.PRODUCTION
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.JSON_LOGS is False
    assert settings.CHUNK_SIZE == 1000


def test_invalid_chunk_overlap_rejected():
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP must be smaller than CHUNK_SIZE"):
        Settings(_env_file=None, CHUNK_SIZE=100, CHUNK_OVERLAP=100)


def test_invalid_environment_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ENV="not-an-environment")