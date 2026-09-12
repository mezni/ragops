import logging
from typing import List

from openai import OpenAI

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
        batch_size: int = 32,
    ) -> List[EmbeddedChunk]:
        """Generates real vector embeddings in batches using OpenRouter."""
        if not chunks:
            return []

        embedded_chunks: List[EmbeddedChunk] = []

        # Process chunks in batches to optimize network efficiency
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.text for c in batch]

            # Call OpenRouter embedding endpoint (retries on 429/timeouts)
            response = embedding_request(self.client, self.model, texts)

            # Map embeddings back to corresponding chunks
            for chunk, data in zip(batch, response.data):
                embedded_chunks.append(
                    EmbeddedChunk(
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        text=chunk.text,
                        embedding=data.embedding,
                        metadata=chunk.metadata
                    )
                )

        return embedded_chunks


# Backward-compatible alias (legacy name from the single-file stage refactor)
EmbeddingStage = Embedder