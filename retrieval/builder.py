"""
retrieval/builder.py
Factory for assembling retrieval pipeline stages into an executable GeneralizedPipeline.
"""

from typing import Any, Optional

from core.logging import get_logger
from core.pipeline import GeneralizedPipeline
from retrieval.stages.generator import GeneratorStage
from retrieval.stages.query_transform import QueryTransformStage
from retrieval.stages.reranker import RerankerStage
from retrieval.stages.retriever import RetrieverStage

logger = get_logger(__name__)


def build_retrieval_pipeline(
    vector_store_adapter: Optional[Any] = None,
    transform_mode: str = "rewrite",
    rerank_top_n: int = 3,
    generator_model: str = "gpt-4o-mini",
) -> GeneralizedPipeline:
    """
    Constructs and configures a sequential RAG retrieval pipeline.

    Stages execution flow:
      1. QueryTransformStage: Rewrites raw query (or generates HyDE).
      2. RetrieverStage: Embeds query & fetches active candidates from vector store.
      3. RerankerStage: Scores & re-ranks candidate chunks via CrossEncoder.
      4. GeneratorStage: Formats context & calls LLM to produce answer.

    Args:
        vector_store_adapter: Active vector store instance (e.g., QdrantAdapter).
        transform_mode: Query transformation mode ('rewrite' or 'hyde').
        rerank_top_n: Number of candidate chunks to keep post-reranking.
        generator_model: LLM model identifier for synthesis.

    Returns:
        GeneralizedPipeline instance ready for execution.
    """
    stages = [
        QueryTransformStage(mode=transform_mode),
        RetrieverStage(),
        RerankerStage(top_n=rerank_top_n),
        GeneratorStage(model_name=generator_model),
    ]

    pipeline = GeneralizedPipeline(
        name="VersionedRetrievalPipeline",
        stages=stages,
    )

    # Attach common execution context dependencies
    if vector_store_adapter:
        pipeline.set_context_variable("vector_store", vector_store_adapter)

    logger.info("Successfully constructed retrieval pipeline", stages=[s.stage_name for s in stages])
    return pipeline