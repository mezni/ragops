"""Document registry: persistent version + liveness bookkeeping.

Each discovered file maps to one ``doc_id``. The registry records:

- ``locator`` / ``data_source`` — where the document came from
- ``is_active`` — False once the source no longer provides the document
- ``active_version`` — the version whose chunks are currently servable
- ``versions`` — ordered history of ``{version, content_hash, indexed_at}``

Every version maps to actual chunks in the vector store, which carry
``version`` and ``is_active`` payload tags. Rolling back a document
therefore only needs its flagged chunks flipped — the old content is
still in the store. Persisted as JSON next to the Chroma store.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _registry_path(persist_dir: str, collection_name: str) -> Path:
    """Registry lives beside the Chroma store, not inside it."""
    return (
        Path(persist_dir).parent
        / f"document_registry_{collection_name}.json"
    )


class DocumentRegistry:
    """JSON-backed store of per-document version + active state."""

    def __init__(self, persist_dir: str, collection_name: str = "aether_wireless_docs"):
        self.path = _registry_path(persist_dir, collection_name)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.is_file():
            with self.path.open("r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        else:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(doc_id)

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._data

    def versions(self, doc_id: str) -> List[Dict[str, Any]]:
        record = self.get(doc_id)
        return list(record["versions"]) if record else []

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def register_version(
        self,
        doc_id: str,
        content_hash: str,
        locator: str,
        data_source: str,
    ) -> int:
        """Records a newly-indexed version. New docs start at version 0;
        every later modification bumps the version by one."""
        record = self.get(doc_id)
        if record is None:
            record = {
                "locator": locator,
                "data_source": data_source,
                "is_active": True,
                "active_version": 0,
                "versions": [],
            }
            self._data[doc_id] = record

        version = (
            max((v["version"] for v in record["versions"]), default=-1) + 1
        )
        record["versions"].append(
            {
                "version": version,
                "content_hash": content_hash,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        record["active_version"] = version
        record["is_active"] = True
        record["locator"] = locator
        record["data_source"] = data_source
        self._save()
        return version

    def set_active(self, doc_id: str, is_active: bool) -> None:
        record = self.get(doc_id)
        if record is None:
            return
        record["is_active"] = is_active
        self._save()

    def set_active_version(self, doc_id: str, version: int) -> None:
        record = self.get(doc_id)
        if record is None:
            return
        record["active_version"] = version
        record["is_active"] = True
        self._save()
        logger.info(
            "[Registry] %s now serves version %d (rollback).",
            doc_id,
            version,
        )