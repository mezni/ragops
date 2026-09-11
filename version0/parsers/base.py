from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    Standardized parsed document output across all parsers.
    
    Attributes:
        payload_id: Associated RawPayload identifier.
        payload_version: Version of the RawPayload from which this was parsed.
        cleaned_text: Extracted, normalized plain text body.
        title: Extracted document title or heading (if available).
        metadata: Format-specific metadata (e.g., page count, header tags).
    """
    payload_id: str
    payload_version: int
    cleaned_text: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseParser(ABC):
    """Abstract interface for format-specific parsers."""

    @abstractmethod
    def parse(self, raw_content: str, payload_id: str, payload_version: int, metadata: Dict[str, Any]) -> Document:
        """
        Parses raw content into a structured Document instance.
        """
        pass