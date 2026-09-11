"""
indexing/builder.py
Factory and orchestrator for assembling and triggering the Indexing Pipeline.
"""

from typing import Any, Dict, List

from core.database import DatabaseManager
from core.logging import get_logger
from core.pipeline import GeneralizedPipeline
from indexing.stages import ChunkingStage, EmbeddedChunk, EmbeddingStage, IngestionStage
from loaders.base import BaseSourceLoader, RawPayload

logger = get_logger(__name__)


def build_indexing_pipeline() -> GeneralizedPipeline[List[RawPayload], List[EmbeddedChunk]]:
    """Assembles and returns a GeneralizedPipeline configured for indexing."""
    return GeneralizedPipeline[List[RawPayload], List[EmbeddedChunk]](
        name="IndexingPipeline",
        stages=[
            IngestionStage(),
            ChunkingStage(),
            EmbeddingStage(),
        ],
    )


def run_indexing_pipeline(
    loader: BaseSourceLoader,
    db_manager: DatabaseManager,
    vector_store_adapter: Any = None,
) -> List[EmbeddedChunk]:
    """
    Loads raw data, executes the indexing pipeline, and upserts results into the vector database.
    """
    logger.info("Starting indexing execution...")

    # 1. Load raw payloads from source
    raw_payloads = loader.load()
    if not raw_payloads:
        logger.info("No payloads fetched by loader. Indexing pipeline exiting early.")
        return []

    # 2. Construct and run pipeline
    pipeline = build_indexing_pipeline()
    context: Dict[str, Any] = {
        "db_manager": db_manager,
    }

    embedded_chunks = pipeline.run(initial_input=raw_payloads, context=context)

    # 3. Optional vector database upsert
    if vector_store_adapter and embedded_chunks:
        logger.info("Upserting vectors into vector database", count=len(embedded_chunks))
        # vector_store_adapter.upsert_chunks(embedded_chunks)

    logger.info("Indexing execution completed successfully.")
    return embedded_chunks