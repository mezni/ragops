"""Unit tests for the retrieval pipeline stages."""

from typing import Any, Dict, List

import pytest

from retrieval.stages import QueryTransformStage, RetrieverStage, RerankerStage, GeneratorStage
from retrieval.stages.models import Query, RetrievedChunk, SynthesizedResponse
from retrieval.builder import build_retrieval_pipeline


# ---------------------------------------------------------------------------
# QueryTransformStage tests
# ---------------------------------------------------------------------------

class TestQueryTransformStage:
    def test_rewrite_mode(self):
        stage = QueryTransformStage(mode="rewrite")
        query = Query(raw_query="  hello world?  ", top_k=5, filters={})
        result = stage.execute(query, {})
        assert result.transformed_query == "hello world"

    def test_hyde_mode_with_mock(self):
        """HyDE mode with no API key falls back to original query."""
        stage = QueryTransformStage(mode="hyde")
        query = Query(raw_query="What is the capital of France?", top_k=5, filters={})
        result = stage.execute(query, {})
        # When OPENAI_API_KEY is not set, falls back to original query
        assert result.transformed_query == "What is the capital of France?"

    def test_normalization_strips_whitespace(self):
        stage = QueryTransformStage(mode="rewrite")
        query = Query(raw_query="  multiple   spaces  ?", top_k=5, filters={})
        result = stage.execute(query, {})
        assert result.transformed_query == "multiple spaces"

    def test_hyde_with_openai_key(monkeypatch):
        """HyDE mode with mock OpenAI key returns generated document."""
        monkeypatch.setattr("retrieval.stages.query_transform.settings.OPENAI_API_KEY", "sk-test")
        import retrieval.stages.query_transform as qt_mod
        # Patch the openai call to avoid actual API calls
        original_chat = openai.chat.completions.create
        def mock_chat(**kwargs):
            return type(
                "obj",
                (object,),
                {"choices": [type("obj", (object,), {"message": type("obj", (object,), {"content": "Hypothetical answer: the capital is Paris."})})]})()
        monkeypatch.setattr(qt_mod, "openai", type("obj", (object,), {"chat": type("obj", (object,), {"completions": type("obj", (object,), {"create": mock_chat})})})())
        
        stage = QueryTransformStage(mode="hyde")
        query = Query(raw_query="What is the capital of France?", top_k=5, filters={})
        result = stage.execute(query, {})
        assert "Paris" in result.transformed_query


# ---------------------------------------------------------------------------
# RetrieverStage tests
# ---------------------------------------------------------------------------

class MockVectorStore:
    """Minimal mock vector store for testing."""
    def search(self, query_vector, top_k=5, filters=None):
        return [
            RetrievedChunk(
                chunk_id="doc1::v1::c0",
                payload_id="doc1",
                payload_version=1,
                chunk_index=0,
                chunk_text="The Eiffel Tower is in Paris.",
                score=0.95,
                metadata={"title": "Paris Facts"},
            ),
            RetrievedChunk(
                chunk_id="doc2::v1::c0",
                payload_id="doc2",
                payload_version=1,
                chunk_index=0,
                chunk_text="The Louvre Museum houses the Mona Lisa.",
                score=0.87,
                metadata={"title": "Louvre Facts"},
            ),
        ]


class TestRetrieverStage:
    def test_retriever_with_mock_store(self):
        stage = RetrieverStage(embedding_model="text-embedding-3-small")
        query = Query(raw_query="Paris landmarks", top_k=5, filters={})
        result = stage.execute(query, {"vector_store": MockVectorStore()})
        assert len(result.chunks) == 2
        assert result.chunks[0].chunk_text == "The Eiffel Tower is in Paris."

    def test_retriever_fallback_no_store(self):
        stage = RetrieverStage(embedding_model="text-embedding-3-small")
        query = Query(raw_query="test query", top_k=3, filters={})
        result = stage.execute(query, {})
        assert len(result.chunks) == 1
        assert "Mock context document" in result.chunks[0].chunk_text

    def test_retriever_with_custom_filters(self):
        stage = RetrieverStage(embedding_model="text-embedding-3-small")
        query = Query(raw_query="test", top_k=5, filters={"author": "test"})
        result = stage.execute(query, {"vector_store": MockVectorStore()})
        assert len(result.chunks) == 2


# ---------------------------------------------------------------------------
# RerankerStage tests
# ---------------------------------------------------------------------------

class TestRerankerStage:
    def test_reranker_with_mock_model(self):
        """Reranker with CrossEncoder available."""
        stage = RerankerStage(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2", top_n=2)
        
        # Monkey-patch the model to return known scores
        stage._reranker_model = type("obj", (object,), {"predict": lambda pairs: [0.95, 0.85]})()
        
        chunks = [
            RetrievedChunk(
                chunk_id="doc1::v1::c0",
                payload_id="doc1",
                payload_version=1,
                chunk_index=0,
                chunk_text="First chunk about Eiffel Tower",
                score=0.7,
                metadata={"title": "Doc 1"},
            ),
            RetrievedChunk(
                chunk_id="doc2::v1::c0",
                payload_id="doc2",
                payload_version=1,
                chunk_index=0,
                chunk_text="Second chunk about Louvre",
                score=0.8,
                metadata={"title": "Doc 2"},
            ),
        ]
        
        result = stage.execute(
            type("obj", (object,), {"chunks": chunks, "query": type("obj", (object,), {"raw_query": "test"})})(),
            {},
        )
        assert len(result.chunks) == 2  # top_n=2 limits output
        # Should be sorted by rerank score descending
        assert result.chunks[0].rerank_score >= result.chunks[1].rerank_score

    def test_reranker_fallback_no_model(self):
        """Reranker without CrossEncoder just truncates to top_n."""
        stage = RerankerStage(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2", top_n=2)
        stage._reranker_model = False  # Simulate model load failure
        
        chunks = [
            RetrievedChunk(
                chunk_id="doc1::v1::c0",
                payload_id="doc1",
                payload_version=1,
                chunk_index=0,
                chunk_text="First chunk",
                score=0.7,
                metadata={"title": "Doc 1"},
            ),
            RetrievedChunk(
                chunk_id="doc2::v1::c0",
                payload_id="doc2",
                payload_version=1,
                chunk_index=0,
                chunk_text="Second chunk",
                score=0.8,
                metadata={"title": "Doc 2"},
            ),
            RetrievedChunk(
                chunk_id="doc3::v1::c0",
                payload_id="doc3",
                payload_version=1,
                chunk_index=0,
                chunk_text="Third chunk",
                score=0.6,
                metadata={"title": "Doc 3"},
            ),
        ]
        
        result = stage.execute(
            type("obj", (object,), {"chunks": chunks, "query": type("obj", (object,), {"raw_query": "test"})})(),
            {},
        )
        assert len(result.chunks) == 2  # top_n=2
        # Should keep original order when fallback
        assert result.chunks[0].chunk_text == "First chunk"


# ---------------------------------------------------------------------------
# GeneratorStage tests
# ---------------------------------------------------------------------------

class TestGeneratorStage:
    def test_generator_with_mock_openai(self, monkeypatch):
        """Generator with mocked OpenAI key produces SynthesizedResponse."""
        monkeypatch.setattr("retrieval.stages.generator.settings.OPENAI_API_KEY", "sk-test")
        
        # Patch the openai call
        import retrieval.stages.generator as gen_mod
        original_chat = openai.chat.completions.create
        def mock_chat(**kwargs):
            return type("obj", (object,), {"choices": [type("obj", (object,), {"message": type("obj", (object,), {"content": "Answer: The capital of France is Paris."})})]})()
        monkeypatch.setattr(openai, "chat", type("obj", (object,), {"completions": type("obj", (object,), {"create": mock_chat})}))
        
        stage = GeneratorStage(model_name="gpt-4o-mini")
        chunks = [
            RetrievedChunk(
                chunk_id="doc1::v1::c0",
                payload_id="doc1",
                payload_version=1,
                chunk_index=0,
                chunk_text="The capital of France is Paris.",
                score=0.95,
                metadata={"title": "Paris Facts"},
            ),
        ]
        result = stage.execute(
            type("obj", (object,), {"query": type("obj", (object,), {"raw_query": "What is the capital of France?"}), "chunks": chunks})(),
            {},
        )
        assert "Paris" in result.answer
        assert result.cited_chunks == chunks

    def test_generator_fallback_no_key(self):
        """Generator fallback when no OpenAI key."""
        stage = GeneratorStage(model_name="gpt-4o-mini")
        chunks = [
            RetrievedChunk(
                chunk_id="doc1::v1::c0",
                payload_id="doc1",
                payload_version=1,
                chunk_index=0,
                chunk_text="The capital of France is Paris.",
                score=0.95,
                metadata={"title": "Paris Facts"},
            ),
        ]
        result = stage.execute(
            type("obj", (object,), {"query": type("obj", (object,), {"raw_query": "What is the capital of France?"}), "chunks": chunks})(),
            {},
        )
        assert "OpenAI key not configured" in result.answer
        assert result.cited_chunks == chunks

    def test_generator_empty_chunks(self):
        """Generator with no chunks produces 'No relevant context found.'"""
        stage = GeneratorStage(model_name="gpt-4o-mini")
        result = stage.execute(
            type("obj", (object,), {"query": type("obj", (object,), {"raw_query": "test"}), "chunks": []})(),
            {},
        )
        assert "No relevant context found" in result.answer


# ---------------------------------------------------------------------------
# build_retrieval_pipeline tests
# ---------------------------------------------------------------------------

class TestBuildRetrievalPipeline:
    def test_pipeline_has_four_stages(self):
        pipeline = build_retrieval_pipeline()
        assert len(pipeline.stages) == 4
        stage_names = [s.stage_name for s in pipeline.stages]
        assert "QueryTransformStage" in stage_names
        assert "RetrieverStage" in stage_names
        assert "RerankerStage" in stage_names
        assert "GeneratorStage" in stage_names

    def test_pipeline_with_custom_params(self):
        pipeline = build_retrieval_pipeline(
            transform_mode="hyde",
            rerank_top_n=5,
            generator_model="gpt-3.5-turbo",
        )
        assert len(pipeline.stages) == 4
        # Check transform mode is set
        transform_stage = pipeline.stages[0]
        assert transform_stage.mode == "hyde"

    def test_pipeline_with_vector_store(self):
        pipeline = build_retrieval_pipeline(vector_store_adapter="mock_adapter")
        # Check context variable was set
        assert pipeline.context.get("vector_store") == "mock_adapter"


# ---------------------------------------------------------------------------
# Integration-style test (no real API keys)
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_end_to_end_pipeline_with_mocks(self):
        """Test the full pipeline runs without errors using mocks."""
        pipeline = build_retrieval_pipeline()
        
        query_input = type("obj", (object,), {
            "raw_query": "Paris landmarks",
            "top_k": 5,
            "filters": {},
            "transformed_query": "Paris landmarks"
        })()
        
        result = pipeline.run(query_input)
        assert isinstance(result, SynthesizedResponse)
        assert result.answer is not None
        assert len(result.cited_chunks) > 0