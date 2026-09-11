"""
retrieval/stages/retriever.py
Vectorizes the transformed query and queries the vector store for candidate chunks.
"""

from typing import Any, Dict, List
from core.config import settings
from core.logging import get_logger
from core.pipeline import PipelineStage
from retrieval.stages.models import Query, RetrievalResult, RetrievedChunk

logger = get_logger(__name__)


class RetrieverStage(PipelineStage[Query, RetrievalResult]):
    """
    Executes vector search via a VectorStoreAdapter and returns raw candidate chunks.
    """

    def __init__(self, embedding_model: str = settings.EMBEDDING_MODEL, stage_name: str = "RetrieverStage"):
        super().__init__(stage_name=stage_name)
        self.embedding_model = embedding_model

    def _embed_query(self, query_text: str) -> List[float]:
        """Vectorizes query string using the configured embedding provider."""
        if settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                res = client.embeddings.create(input=query_text, model=self.embedding_model)
                return res.data[0].embedding
            except Exception as e:
                logger.warning("OpenAI vectorization failed, falling back to mock vector", error=str(e))

        # Fallback deterministic pseudo-embedding
        import hashlib, random
        seed = int(hashlib.md5(query_text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(1536)]

    def execute(self, input_data: Query, context: Dict[str, Any]) -> RetrievalResult:
        query_text = input_data.transformed_query or input_data.raw_query
        query_vector = self._embed_query(query_text)

        vector_store = context.get("vector_store")
        candidate_chunks: List[RetrievedChunk] = []

        if vector_store:
            # Query vector store with active payload filter overrides
            search_results = vector_store.search(
                query_vector=query_vector,
                top_k=input_data.top_k,
                filters=input_data.filters,
            )
            candidate_chunks = search_results
        else:
            logger.warning("No vector store adapter provided in context. Returning mock results.")
            # Fallback mock chunk for isolated testing
            candidate_chunks = [
                RetrievedChunk(
                    chunk_id="mock_doc_1::v1::c0",
                    payload_id="mock_doc_1",
                    payload_version=1,
                    chunk_index=0,
                    chunk_text="Mock context document snippet retrieved for testing purposes.",
                    score=0.89,
                    metadata={"title": "Mock Document"}
                )
            ]

        logger.info("Retriever stage completed", num_retrieved=len(candidate_chunks))
        return RetrievalResult(query=input_data, chunks=candidate_chunks)