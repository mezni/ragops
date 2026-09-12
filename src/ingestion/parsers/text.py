from pathlib import Path

from ingestion.parsers.base import DocumentParser


class TextParser(DocumentParser):
    """Reads plain-text documents verbatim."""

    extensions = (".txt",)

    def extract(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")