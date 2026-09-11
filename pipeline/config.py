"""Validated pipeline configuration (Constitution Article II)."""

from __future__ import annotations

import os
import typing
from enum import StrEnum
from pathlib import Path

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")

_ENV_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "DATABASE_URL": ("db", "database_url"),
    "LOG_LEVEL": ("logging", "level"),
}


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class DbConfig(BaseModel):
    model_config = SettingsConfigDict(extra="forbid")

    database_url: str
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_pre_ping: bool = Field(default=True)
    pool_recycle: int = Field(default=1800, ge=60)
    echo: bool = Field(default=False)

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("database_url must use the postgresql+psycopg:// dialect")
        return value


class LoggingConfig(BaseModel):
    model_config = SettingsConfigDict(extra="forbid")

    level: LogLevel = Field(default=LogLevel.INFO)


def _set_path(data: dict, path: tuple[str, ...], value: typing.Any) -> None:
    target = data
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def _load_source_values(yaml_file: Path, env_file: Path | None) -> dict:
    """Merge config.yaml + .env + os.environ with documented precedence.

    Precedence: environment > .env > config.yaml. Keys are projected onto the
    nested schema via ``_ENV_FIELD_MAP``.
    """
    data: dict = {}
    if yaml_file.exists():
        loaded = yaml.safe_load(yaml_file.read_text()) or {}
        if isinstance(loaded, dict):
            data.update(loaded)

    if env_file is not None and env_file.exists():
        for env_key, path in _ENV_FIELD_MAP.items():
            value = dotenv_values(env_file).get(env_key)
            if value is not None:
                _set_path(data, path, value)

    for env_key, path in _ENV_FIELD_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            _set_path(data, path, value)

    return data


class YamlEnvSettingsSource(PydanticBaseSettingsSource):
    """Settings source honoring env > .env > config.yaml precedence."""

    def __init__(self, settings_cls, path: Path) -> None:
        super().__init__(settings_cls)
        self._path = path

    def get_field_value(self, field, field_name: str) -> tuple[typing.Any, str, bool]:
        return None, "", False

    def __call__(self) -> dict[str, typing.Any]:
        return _load_source_values(self._path, DEFAULT_ENV_PATH)


class PipelineConfig(BaseSettings):
    """Root configuration, validated at construction.

    Source precedence: environment > .env > config.yaml > defaults.
    Env overrides: ``DATABASE_URL`` -> ``db.database_url``,
    ``LOG_LEVEL`` -> ``logging.level``.
    """

    model_config = SettingsConfigDict(extra="forbid")

    db: DbConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, YamlEnvSettingsSource(settings_cls, DEFAULT_CONFIG_PATH))


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
    """Load and validate configuration from a specific YAML path.

    Raises validation errors at construction (fail fast) per the
    config-schema contract.
    """

    class _ConfigAtPath(PipelineConfig):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (init_settings, YamlEnvSettingsSource(settings_cls, config_path))

    return _ConfigAtPath()