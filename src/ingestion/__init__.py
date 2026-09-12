"""RAG ingestion pipeline for Aether Wireless.

Public API keeps the original flat-module surface so existing callers
still work: ``from ingestion import ...``.
"""

from core.logging import configure_logging
from ingestion.pipeline import main, RAGIndexingPipeline
from ingestion.schemas import Document, EmbeddedChunk, TextChunk
from ingestion.stages import (
    Chunker,
    ChunkerStage,
    DocumentLoader,
    Embedder,
    EmbeddingStage,
    IngestionStage,
    VectorStore,
    VectorStoreStage,
)

__all__ = [
    "Chunker",
    "ChunkerStage",
    "Document",
    "DocumentLoader",
    "EmbeddedChunk",
    "Embedder",
    "EmbeddingStage",
    "IngestionStage",
    "RAGIndexingPipeline",
    "TextChunk",
    "VectorStore",
    "VectorStoreStage",
    "configure_logging",
    "main",
]