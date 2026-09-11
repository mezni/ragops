"""
retrieval/vector_store/qdrant.py
Qdrant vector store adapter supporting metadata payload filtering and active version checks.
"""

from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.config import settings
from core.logging import get_logger
from retrieval.stages.models import RetrievedChunk

logger = get_logger(__name__)


class QdrantAdapter:
    """
    Adapter for interacting with Qdrant Vector Database, applying payload-level filters
    to enforce version isolation during similarity search.
    """

    def __init__(
        self,
        collection_name: str = "rag_documents",
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.url = url or getattr(settings, "QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or getattr(settings, "QDRANT_API_KEY", None)

        self.client = QdrantClient(url=self.url, api_key=self.api_key)
        logger.info("Initialized QdrantAdapter", collection=self.collection_name, url=self.url)

    def _build_payload_filter(self, user_filters: Optional[Dict[str, Any]] = None) -> qmodels.Filter:
        """
        Constructs Qdrant FieldConditions to filter out inactive/deleted document versions.

        Default Enforcement:
          - is_active == True
          - is_deleted == False
        """
        must_conditions: List[qmodels.FieldCondition] = [
            qmodels.FieldCondition(
                key="is_active",
                match=qmodels.MatchValue(value=True),
            ),
            qmodels.FieldCondition(
                key="is_deleted",
                match=qmodels.MatchValue(value=False),
            ),
        ]

        # Ingest custom user filters dynamically (e.g. payload_id, payload_version)
        if user_filters:
            for key, value in user_filters.items():
                if isinstance(value, list):
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchAny(any=value),
                        )
                    )
                else:
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value),
                        )
                    )

        return qmodels.Filter(must=must_conditions)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        """
        Executes vector search in Qdrant with active-version filtering.
        """
        qdrant_filter = self._build_payload_filter(user_filters=filters)

        try:
            search_response = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )

            retrieved_chunks: List[RetrievedChunk] = []
            for hit in search_response:
                payload = hit.payload or {}

                chunk = RetrievedChunk(
                    chunk_id=str(hit.id),
                    payload_id=payload.get("payload_id", "unknown_doc"),
                    payload_version=payload.get("version", 1),
                    chunk_index=payload.get("chunk_index", 0),
                    chunk_text=payload.get("text", ""),
                    score=float(hit.score),
                    metadata=payload.get("metadata", {}),
                )
                retrieved_chunks.append(chunk)

            logger.info("Qdrant search succeeded", result_count=len(retrieved_chunks))
            return retrieved_chunks

        except Exception as e:
            logger.error("Failed to query Qdrant collection", error=str(e))
            raise RuntimeError(f"Qdrant query execution error: {str(e)}") from e
