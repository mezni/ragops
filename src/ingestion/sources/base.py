from abc import ABC, abstractmethod
from typing import List

from ingestion.schemas import SourceReference


class DocumentSource(ABC):
    """A discoverable data location.

    Concrete sources (filesystem directory, RDBMS table, external API)
    produce :class:`SourceReference` objects describing what can be
    ingested, decoupled from how each document is parsed afterwards.
    """

    source_type: str = "unknown"

    @abstractmethod
    def discover(self) -> List[SourceReference]:
        """Return references to every document available from this source."""