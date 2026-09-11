from core.database import DatabaseManager


def test_compute_hash_deterministic():
    assert DatabaseManager.compute_hash("hello world") == DatabaseManager.compute_hash(
        "hello world"
    )


def test_compute_hash_is_sha256_hex():
    assert len(DatabaseManager.compute_hash("hello world")) == 64


def test_compute_hash_content_sensitive():
    assert DatabaseManager.compute_hash("a") != DatabaseManager.compute_hash("b")


def test_compute_hash_accepts_str_and_bytes():
    assert DatabaseManager.compute_hash(b"bytes") == DatabaseManager.compute_hash("bytes")