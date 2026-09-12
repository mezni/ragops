from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple


class DocumentParser(ABC):
    """Extracts raw text from a single document file.

    Each concrete parser owns one format (or family of formats) and
    knows how to pull out text — and, when relevant, tables rendered as
    Markdown grids — so the loader stays format-agnostic.
    """

    extensions: Tuple[str, ...] = ()

    @abstractmethod
    def extract(self, path: Path) -> str:
        """Return the raw text (tables included) contained in ``path``."""