from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Raw document extracted from disk before chunking."""
    doc_id: str = Field(..., description="Unique identifier (e.g., file name)")
    content: str = Field(..., min_length=1, description="Extracted raw text")
    source: str = Field(..., description="Absolute or relative file path")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")


class TextChunk(BaseModel):
    """Processed text chunk ready for embedding."""
    chunk_id: str = Field(..., description="Unique identifier (doc_id_chunk_N)")
    doc_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., min_length=1, description="Chunked text slice")
    chunk_index: int = Field(..., ge=0, description="Sequential index")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Merged metadata")


class EmbeddedChunk(BaseModel):
    """Vectorized chunk ready for database insertion."""
    chunk_id: str
    doc_id: str
    text: str
    embedding: List[float] = Field(..., description="Dense vector embedding")
    metadata: Dict[str, Any]