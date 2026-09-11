from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RawPayload(BaseModel):
    """
    Standardized payload format output by all source loaders.
    
    Attributes:
        payload_id: Unique identifier for the source item (e.g., file path or DB primary key).
        source_type: Category of source (e.g., 'filesystem', 'database', 'api').
        source_uri: Canonical location indicator.
        raw_content: Unparsed text or string representation of source body.
        content_type: MIME type or format hint (e.g., 'text/plain', 'application/pdf').
        metadata: Extra contextual key-value pairs (e.g., file size, author, headers).
    """
    payload_id: str
    source_type: str
    source_uri: str
    raw_content: str
    content_type: str = "text/plain"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseSourceLoader(ABC):
    """Abstract interface for all data source loaders."""

    @abstractmethod
    def load(self) -> List[RawPayload]:
        """Fetches data from the source and returns a list of RawPayload instances."""
        pass