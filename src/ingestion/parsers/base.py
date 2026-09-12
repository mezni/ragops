from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple


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

    @property
    def engine_label(self) -> str:
        """Human/audit-readable parser id, e.g. ``PDFParser@pdfplumber-0.11``."""
        import importlib.metadata

        lib = getattr(self, "library_name", None)
        if not lib:
            return type(self).__name__
        try:
            version = importlib.metadata.version(lib)
        except importlib.metadata.PackageNotFoundError:
            version = "?"
        return f"{type(self).__name__}@{lib}-{version}"

    def page_count(self, path: Path) -> Optional[int]:
        """Return the physical page count for formats that support it.

        Defaults to None (unknown). PDF parsers override this to enable
        the ``total_pages`` document-metadata field.
        """
        return None