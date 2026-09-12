import logging
from typing import List, Optional

from openai import OpenAI

from core.config import get_settings
from core.resiliency import embedding_request
from ingestion.schemas import EmbeddedChunk, TextChunk

logger = logging.getLogger(__name__)


class Embedder:
    """Generates real vector embeddings for TextChunks via OpenRouter."""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def run(
        self,
        chunks: List[TextChunk],
        batch_size: Optional[int] = None,
    ) -> List[EmbeddedChunk]:
        """Generates real vector embeddings in batches using OpenRouter."""
        if not chunks:
            return []

        batch_size = batch_size or get_settings().embedding.batch_size
        embedded_chunks: List[EmbeddedChunk] = []

        # Process chunks in batches to optimize network efficiency
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]

            # Call OpenRouter embedding endpoint (retries on 429/timeouts)
            response = embedding_request(self.client, self.model, texts)

            # Map embeddings back to corresponding chunks
            for chunk, data in zip(batch, response.data):
                # Flatten typed metadata to plain dict for Chroma (flat keys),
                # then stamp the vector-model provenance (audit lineage).
                meta = chunk.metadata.model_dump()
                meta["embedding_model"] = self.model
                meta["embedding_dimensions"] = len(data.embedding)
                meta["distance_metric"] = get_settings().chroma.hnsw_space
                meta["tokenizer_name"] = get_settings().embedding.tokenizer
                embedded_chunks.append(
                    EmbeddedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        text=chunk.text,
                        embedding=data.embedding,
                        metadata=meta,
                    )
                )

        return embedded_chunks


# Backward-compatible alias (legacy name from the single-file stage refactor)
EmbeddingStage = Embedder