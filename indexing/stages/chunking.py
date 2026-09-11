"""
indexing/stages/chunking.py
Splits Documents into overlapping text chunks.
"""

from typing import Any, Dict, List

from core.config import settings
from core.logging import get_logger
from core.pipeline import PipelineStage
from indexing.stages.models import TextChunk
from parsers.base import Document

logger = get_logger(__name__)


class ChunkingStage(PipelineStage[List[Document], List[TextChunk]]):
    """
    Applies sliding-window chunking to parsed Documents.
    """

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
        stage_name: str = "ChunkingStage",
    ):
        super().__init__(stage_name=stage_name)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def execute(self, input_data: List[Document], context: Dict[str, Any]) -> List[TextChunk]:
        all_chunks: List[TextChunk] = []

        for doc in input_data:
            text = doc.cleaned_text
            if not text:
                continue

            # Sliding character-window chunking implementation
            step = max(1, self.chunk_size - self.chunk_overlap)
            chunks_text = [text[i : i + self.chunk_size] for i in range(0, len(text), step)]

            for idx, chunk_str in enumerate(chunks_text):
                chunk_id = f"{doc.payload_id}::v{doc.payload_version}::c{idx}"
                chunk = TextChunk(
                    chunk_id=chunk_id,
                    payload_id=doc.payload_id,
                    payload_version=doc.payload_version,
                    chunk_index=idx,
                    chunk_text=chunk_str,
                    metadata={
                        **doc.metadata,
                        "title": doc.title,
                        "payload_id": doc.payload_id,
                        "version": doc.payload_version,
                    },
                )
                all_chunks.append(chunk)

        logger.info("Chunking stage completed", total_chunks=len(all_chunks))
        return all_chunks