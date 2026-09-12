import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import get_settings
from ingestion.schemas import EmbeddedChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Persistent ChromaDB vector store. Survives process restarts."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        cfg = get_settings().chroma
        persist_dir = persist_dir or cfg.persist_dir
        collection_name = collection_name or cfg.collection_name

        chroma_dir = Path(persist_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=cfg.anonymized_telemetry),
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": cfg.hnsw_space},
        )

    @property
    def count(self) -> int:
        return self.collection.count()

    def upsert(
        self,
        embedded_chunks: List[EmbeddedChunk],
        version: Optional[int] = None,
        is_active: bool = True,
    ) -> int:
        """Persists embedded chunks into the ChromaDB vector store on disk,
        stamping every payload with ``version`` and ``is_active`` tags."""
        if not embedded_chunks:
            return 0

        version = version if version is not None else 0
        self.collection.upsert(
            ids=[c.chunk_id for c in embedded_chunks],
            embeddings=[c.embedding for c in embedded_chunks],
            documents=[c.text for c in embedded_chunks],
            metadatas=[
                {
                    **c.metadata,
                    "doc_id": c.doc_id,
                    "version": version,
                    "is_active": is_active,
                }
                for c in embedded_chunks
            ],
        )
        return len(embedded_chunks)

    def query(
        self,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        active_only: bool = True,
    ) -> Dict[str, Any]:
        """Returns top-K context blocks from the persistent store.

        Only active chunks are considered by default, so deactivated /
        rolled-back documentation never surfaces in answers.
        """
        top_k = top_k or get_settings().search.top_k
        where = {"is_active": True} if active_only else None
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def get_document_hashes(self, doc_id: str) -> Set[str]:
        """Returns the set of content hashes for a doc_id's ACTIVE chunks."""
        result = self.collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )

        hashes: Set[str] = set()
        for metadata in result.get("metadatas", []) or []:
            if metadata.get("is_active", True) is False:
                continue
            content_hash = metadata.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return hashes

    def get_document_versions(self, doc_id: str) -> List[Dict[str, Any]]:
        """Returns distinct ``{version, is_active}`` tags for a doc_id."""
        result = self.collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )

        seen: Dict[int, bool] = {}
        for metadata in result.get("metadatas", []) or []:
            version = metadata.get("version")
            if version is not None:
                seen[version] = metadata.get("is_active", False)
        return [
            {"version": version, "is_active": is_active}
            for version, is_active in sorted(seen.items())
        ]

    def deactivate_document(self, doc_id: str) -> int:
        """Flips every stored chunk of ``doc_id`` to is_active=False.

        Old content is kept (so it can be rolled back later) but is no
        longer served by search. Returns the number of chunks flipped.
        """
        return self._set_active_version(doc_id, version=None)

    def activate_version(self, doc_id: str, version: int) -> int:
        """Re-enables the chunks of a specific version; all other versions
        of the doc_id are deactivated in the same pass."""
        return self._set_active_version(doc_id, version=version)

    def _set_active_version(
        self,
        doc_id: str,
        version: Optional[int],
    ) -> int:
        result = self.collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )
        ids = result.get("ids", []) or []
        metadatas = result.get("metadatas", []) or []
        if not ids:
            return 0

        flipped = 0
        for chunk_id, metadata in zip(ids, metadatas):
            chunk_version = metadata.get("version")
            if version is None:
                is_active = False
            else:
                is_active = chunk_version == version
            if metadata.get("is_active") == is_active:
                continue
            self.collection.update(
                ids=[chunk_id],
                metadatas=[{"is_active": is_active}],
            )
            flipped += 1
        return flipped

    def delete_document(self, doc_id: str) -> int:
        """Deletes every chunk belonging to a doc_id. Returns chunks removed."""
        result = self.collection.get(where={"doc_id": doc_id})
        ids = result.get("ids", []) or []

        if ids:
            self.collection.delete(ids=ids)

        return len(ids)


# Backward-compatible alias (legacy name from the single-file stage refactor)
VectorStoreStage = VectorStore