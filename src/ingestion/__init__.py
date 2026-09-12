"""RAG ingestion pipeline for Aether Wireless.

Public API keeps the original flat-module surface so existing callers
still work: ``from ingestion import ...``.
"""

from core.logging import configure_logging
from ingestion.pipeline import main, RAGIndexingPipeline
from ingestion.schemas import Document, EmbeddedChunk, SourceReference, TextChunk
from ingestion.sources import DocumentSource, FileSystemSource
from ingestion.stages import (
    Chunker,
    ChunkerStage,
    DocumentLoader,
    DocumentRegistry,
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
    "DocumentRegistry",
    "DocumentSource",
    "EmbeddedChunk",
    "Embedder",
    "EmbeddingStage",
    "FileSystemSource",
    "IngestionStage",
    "RAGIndexingPipeline",
    "SourceReference",
    "TextChunk",
    "VectorStore",
    "VectorStoreStage",
    "configure_logging",
    "main",
]