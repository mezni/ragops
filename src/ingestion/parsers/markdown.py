from pathlib import Path

from ingestion.parsers.base import DocumentParser


class MarkdownParser(DocumentParser):
    """Reads Markdown documents verbatim (headings and lists preserved)."""

    extensions = (".md", ".markdown")

    def extract(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")