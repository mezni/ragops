import logging

from core import config
from core.config import build_settings, get_settings, reload_settings


def _restore():
    reload_settings()


def test_defaults_match_config_file():
    # ragops.toml in the repo root declares the exact same tunables as the
    # code defaults, so a raw parse should produce consistent values.
    cfg = build_settings()
    assert cfg.chunking.chunk_size == 500
    assert cfg.chunking.chunk_overlap == 50
    assert cfg.embedding.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert cfg.embedding.model == "openai/text-embedding-3-small"
    assert cfg.embedding.batch_size == 32
    assert cfg.chroma.persist_dir == "data/processed/chroma"
    assert cfg.chroma.collection_name == "aether_wireless_docs"
    assert cfg.search.top_k == 5
    assert cfg.resiliency.max_attempts == 5
    assert cfg.resiliency.wait_jitter == 2.0
    assert cfg.ocr.dpi == 200
    assert cfg.sources.patterns == ("*.pdf", "*.txt", "*.md")
    assert cfg.metadata.tenant_id == "default_tenant"
    assert cfg.metadata.access_roles == ("public",)
    assert cfg.metadata.classification == "internal"
    assert cfg.metadata.doc_type == "document"
    assert cfg.metadata.language == "en"
    assert cfg.metadata.domain is None
    assert cfg.logging.level == logging.INFO
    assert cfg.logging.root_level == logging.WARNING


def test_logging_level_string_coerced_from_toml():
    # ragops.toml uses human-friendly "INFO"; the dataclass holds an int.
    assert get_settings().logging.level == logging.INFO


def test_env_override_precedence(monkeypatch):
    monkeypatch.setenv("RAGOPS_CHUNKING_CHUNK_SIZE", "750")
    monkeypatch.setenv("RAGOPS_CHROMA_ANONYMIZED_TELEMETRY", "true")
    monkeypatch.setenv("RAGOPS_SOURCES_PATTERNS", "*.pdf,*.docx")
    monkeypatch.setenv("RAGOPS_METADATA_TENANT_ID", "acme-01")
    monkeypatch.setenv("RAGOPS_METADATA_ACCESS_ROLES", "billing_admin,support_tier_2")
    monkeypatch.setenv("RAGOPS_METADATA_CLASSIFICATION", "confidential")
    monkeypatch.setenv("RAGOPS_LOGGING_LEVEL", "DEBUG")

    try:
        cfg = config.reload_settings()
        assert cfg.chunking.chunk_size == 750
        assert cfg.chroma.anonymized_telemetry is True
        assert cfg.sources.patterns == ("*.pdf", "*.docx")
        assert cfg.metadata.tenant_id == "acme-01"
        assert cfg.metadata.access_roles == ("billing_admin", "support_tier_2")
        assert cfg.metadata.classification == "confidential"
        assert cfg.logging.level == logging.DEBUG
    finally:
        _restore()


def test_custom_config_file(tmp_path):
    custom = tmp_path / "custom.toml"
    custom.write_text(
        "[chunking]\nchunk_size = 777\n[resiliency]\nmax_attempts = 9\n",
        encoding="utf-8",
    )
    try:
        cfg = config.reload_settings(custom)
        assert cfg.chunking.chunk_size == 777
        # Values absent from the custom file keep their ragops.toml defaults.
        assert cfg.resiliency.max_attempts == 9
        assert cfg.chunking.chunk_overlap == 50
    finally:
        _restore()


def test_unknown_keys_are_ignored(tmp_path):
    custom = tmp_path / "odd.toml"
    custom.write_text("[chunking]\nnonsense = true\n", encoding="utf-8")
    try:
        cfg = config.reload_settings(custom)
        assert cfg.chunking.chunk_size == 500
    finally:
        _restore()