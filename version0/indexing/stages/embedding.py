"""
indexing/stages/embedding.py
Vectorizes text chunks using OpenAI or custom embedding providers.
"""

from typing import Any, Dict, List

from core.config import settings
from core.logging import get_logger
from core.pipeline import PipelineStage
from indexing.stages.models import EmbeddedChunk, TextChunk

logger = get_logger(__name__)


class EmbeddingStage(PipelineStage[List[TextChunk], List[EmbeddedChunk]]):
    """
    Generates embeddings for TextChunks and packages them into EmbeddedChunk objects.
    """

    def __init__(self, model_name: str = settings.EMBEDDING_MODEL, stage_name: str = "EmbeddingStage"):
        super().__init__(stage_name=stage_name)
        self.model_name = model_name

    def _generate_embedding(self, text: str) -> List[float]:
        """Calls OpenAI API or generates deterministic mock embeddings for testing."""
        if settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.embeddings.create(input=text, model=self.model_name)
                return response.data[0].embedding
            except Exception as e:
                logger.warning("OpenAI embedding API call failed, using fallback vector", error=str(e))

        # Fallback pseudo-embedding (1536 dimensions) for testing/development
        import hashlib
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        import random
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(1536)]

    def execute(self, input_data: List[TextChunk], context: Dict[str, Any]) -> List[EmbeddedChunk]:
        embedded_chunks: List[EmbeddedChunk] = []

        for chunk in input_data:
            vector = self._generate_embedding(chunk.chunk_text)
            embedded = EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                payload_id=chunk.payload_id,
                payload_version=chunk.payload_version,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                vector=vector,
                metadata=chunk.metadata,
            )
            embedded_chunks.append(embedded)

        logger.info("Embedding stage completed", total_embedded=len(embedded_chunks))
        return embedded_chunks