"""
retrieval/stages/reranker.py
Re-ranks retrieved candidate chunks using a CrossEncoder model for enhanced precision.
"""

from typing import Any, Dict, List
from core.logging import get_logger
from core.pipeline import PipelineStage
from retrieval.stages.models import RetrievalResult

logger = get_logger(__name__)


class RerankerStage(PipelineStage[RetrievalResult, RetrievalResult]):
    """
    Applies Cross-Encoder reranking over retrieved candidate chunks.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", top_n: int = 3, stage_name: str = "RerankerStage"):
        super().__init__(stage_name=stage_name)
        self.model_name = model_name
        self.top_n = top_n
        self._reranker_model = None

    def _get_model(self):
        """Lazy loads CrossEncoder model."""
        if self._reranker_model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker_model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning("Failed to initialize CrossEncoder. Reranking will be skipped.", error=str(e))
                self._reranker_model = False
        return self._reranker_model

    def execute(self, input_data: RetrievalResult, context: Dict[str, Any]) -> RetrievalResult:
        chunks = input_data.chunks
        if not chunks:
            return input_data

        model = self._get_model()
        query_text = input_data.query.raw_query

        if model:
            # Prepare pairs of (query, chunk_text)
            pairs = [[query_text, chunk.chunk_text] for chunk in chunks]
            scores = model.predict(pairs)

            for idx, score in enumerate(scores):
                chunks[idx].rerank_score = float(score)

            # Sort chunks by cross-encoder score descending
            chunks.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)
            input_data.chunks = chunks[: self.top_n]
            logger.info("Reranking completed", original_count=len(pairs), output_count=len(input_data.chunks))
        else:
            # Fallback: slice top_n without reordering
            input_data.chunks = chunks[: self.top_n]

        return input_data