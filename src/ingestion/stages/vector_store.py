import logging
from pathlib import Path
from typing import Any, Dict, List, Set

import chromadb
from chromadb.config import Settings

from ingestion.schemas import EmbeddedChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Persistent ChromaDB vector store. Survives process restarts."""

    def __init__(
        self,
        persist_dir: str = "data/processed/chroma",
        collection_name: str = "aether_wireless_docs",
    ):
        chroma_dir = Path(persist_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self.collection.count()

    def upsert(self, embedded_chunks: List[EmbeddedChunk]) -> int:
        """Persists embedded chunks into the ChromaDB vector store on disk."""
        if not embedded_chunks:
            return 0

        self.collection.upsert(
            ids=[c.chunk_id for c in embedded_chunks],
            embeddings=[c.embedding for c in embedded_chunks],
            documents=[c.text for c in embedded_chunks],
            metadatas=[
                {**c.metadata, "doc_id": c.doc_id} for c in embedded_chunks
            ],
        )
        return len(embedded_chunks)

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Returns top-K context blocks from the persistent store."""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

    def get_document_hashes(self, doc_id: str) -> Set[str]:
        """Returns the set of content hashes currently stored for a doc_id."""
        result = self.collection.get(
            where={"doc_id": doc_id},
            include=["metadatas"],
        )

        hashes: Set[str] = set()
        for metadata in result.get("metadatas", []) or []:
            content_hash = metadata.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return hashes

    def delete_document(self, doc_id: str) -> int:
        """Deletes every chunk belonging to a doc_id. Returns chunks removed."""
        result = self.collection.get(where={"doc_id": doc_id})
        ids = result.get("ids", []) or []

        if ids:
            self.collection.delete(ids=ids)

        return len(ids)


# Backward-compatible alias (legacy name from the single-file stage refactor)
VectorStoreStage = VectorStore