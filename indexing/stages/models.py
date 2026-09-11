from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TextChunk(BaseModel):
    """Represents a discrete text segment extracted from a Document."""

    chunk_id: str
    payload_id: str
    payload_version: int
    chunk_index: int
    chunk_text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmbeddedChunk(BaseModel):
    """Represents a TextChunk with its generated vector embedding."""

    chunk_id: str
    payload_id: str
    payload_version: int
    chunk_index: int
    chunk_text: str
    vector: List[float]
    metadata: Dict[str, Any] = Field(default_factory=dict)