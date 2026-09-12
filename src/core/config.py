"""Centralized configuration for the RAG ingestion pipeline.

Single source of truth for every tunable in the codebase — chunking,
embedding, vector store, search, sources, resiliency, OCR and logging.

Precedence (lowest to highest):

1. Code defaults (the dataclass definitions here)
2. A TOML file: ``ragops.toml`` in the project root, or a custom path in
   the ``RAGOPS_CONFIG`` environment variable
3. ``RAGOPS_<SECTION>_<FIELD>`` environment variables (e.g.
   ``RAGOPS_CHUNKING_CHUNK_SIZE=750``, ``RAGOPS_LOGGING_LEVEL=DEBUG``)

Consumers call :func:`get_settings` and read from the returned
:class:`Settings` object instead of hard-coding their own defaults.
"""

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple, Type

# Repository root (this file lives at src/core/config.py).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DEFAULT_CONFIG_FILE = "ragops.toml"
_ENV_PREFIX = "RAGOPS_"


# ---------------------------------------------------------------------
# Settings groups
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class PathsSettings:
    """Filesystem locations (tunable via RAGOPS_PATHS_*)."""

    project_root: Path = _PROJECT_ROOT
    raw_dir: str = "data/raw"


@dataclass(frozen=True)
class ChunkingSettings:
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: Tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")


@dataclass(frozen=True)
class EmbeddingSettings:
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/text-embedding-3-small"
    batch_size: int = 32


@dataclass(frozen=True)
class ChromaSettings:
    persist_dir: str = "data/processed/chroma"
    collection_name: str = "aether_wireless_docs"
    hnsw_space: str = "cosine"
    anonymized_telemetry: bool = False


@dataclass(frozen=True)
class SearchSettings:
    top_k: int = 5
    sanity_query: str = "how long does a billing dispute investigation take?"


@dataclass(frozen=True)
class SourcesSettings:
    patterns: Tuple[str, ...] = ("*.pdf", "*.txt", "*.md")


@dataclass(frozen=True)
class ResiliencySettings:
    max_attempts: int = 5
    wait_initial: float = 1.0
    wait_max: float = 30.0
    wait_exp_base: float = 2.0
    wait_jitter: float = 2.0


@dataclass(frozen=True)
class OcrSettings:
    dpi: int = 200


@dataclass(frozen=True)
class LoggingSettings:
    level: int = logging.INFO
    root_level: int = logging.WARNING
    format: str = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"
    console_handler_name: str = "ragops-console"
    package_loggers: Tuple[str, ...] = ("ingestion", "core", "utils")
    hash_preview_len: int = 8
    snippet_length: int = 200


@dataclass(frozen=True)
class Settings:
    """Top-level container for every pipeline tunable."""

    paths: PathsSettings = field(default_factory=PathsSettings)
    chunking: ChunkingSettings = field(default_factory=ChunkingSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    chroma: ChromaSettings = field(default_factory=ChromaSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    sources: SourcesSettings = field(default_factory=SourcesSettings)
    resiliency: ResiliencySettings = field(default_factory=ResiliencySettings)
    ocr: OcrSettings = field(default_factory=OcrSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


# Section name -> dataclass, in the order they appear in TOML.
_SECTIONS: Tuple[Tuple[str, Type[Any]], ...] = (
    ("paths", PathsSettings),
    ("chunking", ChunkingSettings),
    ("embedding", EmbeddingSettings),
    ("chroma", ChromaSettings),
    ("search", SearchSettings),
    ("sources", SourcesSettings),
    ("resiliency", ResiliencySettings),
    ("ocr", OcrSettings),
    ("logging", LoggingSettings),
)


# ---------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------

def _coerce_value(field_name: str, value: Any, template: Any) -> Any:
    """Converts a TOML/env value to the type of the dataclass default."""
    if isinstance(template, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    if isinstance(template, tuple):
        if isinstance(value, str):
            value = value.split(",")
        return tuple(str(item).strip() for item in value)

    if isinstance(template, int):
        if isinstance(value, int):
            return value
        raw = str(value).strip()
        # Human-friendly logging levels, e.g. "INFO" / "DEBUG".
        if "level" in field_name and not raw.lstrip("-").isdigit():
            resolved = logging.getLevelName(raw.upper())
            if isinstance(resolved, int):
                return resolved
        return int(raw)

    if isinstance(template, float):
        return float(value)

    return value


# ---------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------

def _config_path() -> Optional[Path]:
    """Returns the active TOML config path, or None."""
    custom = os.getenv("RAGOPS_CONFIG")
    if custom:
        return Path(custom)
    candidate = _PROJECT_ROOT / _DEFAULT_CONFIG_FILE
    return candidate if candidate.is_file() else None


def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _apply_env() -> dict:
    """Collects RAGOPS_<SECTION>_<FIELD> overrides into a nested dict."""
    overrides: dict = {}
    for section, cls in _SECTIONS:
        for name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            env_name = f"{_ENV_PREFIX}{section}_{name}".upper()
            raw = os.getenv(env_name)
            if raw is None:
                continue
            overrides.setdefault(section, {})[name] = raw
    return overrides


def build_settings(config_file: Optional[Path] = None) -> Settings:
    """Builds the :class:`Settings` from defaults + TOML + environment."""
    # 1. Code defaults.
    data: dict = {section: {} for section, _ in _SECTIONS}

    # 2. Optional TOML file.
    path = config_file or _config_path()
    if path is not None:
        raw = _load_toml(path)
        for section, cls in _SECTIONS:
            if section in raw:
                data[section].update(raw[section])

    # 3. Environment variables (highest precedence).
    for section, fields in _apply_env().items():
        data[section].update(fields)

    # Build each section dataclass, coercing values to the right types.
    sections: dict = {}
    for section, cls in _SECTIONS:
        defaults = cls.__dataclass_fields__  # type: ignore[attr-defined]
        values = {
            name: _coerce_value(name, value, defaults[name].default)
            for name, value in data[section].items()
            if name in defaults
        }
        sections[section] = cls(**values)

    return Settings(**sections)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Returns the shared, lazily-loaded settings singleton."""
    global _settings
    if _settings is None:
        _settings = build_settings()
    return _settings


def reload_settings(config_file: Optional[Path] = None) -> Settings:
    """Rebuilds the settings singleton (used by tests / runtime reload)."""
    global _settings
    _settings = build_settings(config_file)
    return _settings