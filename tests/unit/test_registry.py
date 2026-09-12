from ingestion.stages.registry import DocumentRegistry


def test_new_doc_starts_at_version_zero(tmp_path):
    reg = DocumentRegistry(str(tmp_path / "chroma"))
    version = reg.register_version("AW-1", "hash-a", "/docs/AW-1.txt", "filesystem")

    assert version == 0
    record = reg.get("AW-1")
    assert record["is_active"] is True
    assert record["active_version"] == 0
    assert len(record["versions"]) == 1


def test_modification_bumps_version(tmp_path):
    reg = DocumentRegistry(str(tmp_path / "chroma"))
    reg.register_version("AW-1", "hash-a", "/docs/AW-1.txt", "filesystem")
    version = reg.register_version("AW-1", "hash-b", "/docs/AW-1.txt", "filesystem")

    assert version == 1
    record = reg.get("AW-1")
    assert record["active_version"] == 1
    assert [v["content_hash"] for v in record["versions"]] == ["hash-a", "hash-b"]


def test_set_active_toggles_liveness(tmp_path):
    reg = DocumentRegistry(str(tmp_path / "chroma"))
    reg.register_version("AW-1", "hash-a", "/docs/AW-1.txt", "filesystem")

    reg.set_active("AW-1", False)
    assert reg.get("AW-1")["is_active"] is False

    reg.set_active("AW-1", True)
    assert reg.get("AW-1")["is_active"] is True


def test_set_active_version_records_rollback(tmp_path):
    reg = DocumentRegistry(str(tmp_path / "chroma"))
    reg.register_version("AW-1", "hash-a", "/docs/AW-1.txt", "filesystem")
    reg.register_version("AW-1", "hash-b", "/docs/AW-1.txt", "filesystem")

    reg.set_active_version("AW-1", 0)
    record = reg.get("AW-1")
    assert record["active_version"] == 0
    assert record["is_active"] is True


def test_registry_persists_across_instances(tmp_path):
    persist_dir = str(tmp_path / "chroma")
    DocumentRegistry(persist_dir).register_version(
        "AW-1", "hash-a", "/docs/AW-1.txt", "filesystem"
    )

    reloaded = DocumentRegistry(persist_dir)
    assert reloaded.get("AW-1")["active_version"] == 0
    assert reloaded.versions("AW-1")[0]["content_hash"] == "hash-a"