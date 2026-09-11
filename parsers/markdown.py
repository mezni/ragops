import re
from typing import Any, Dict
from core.logging import get_logger
from parsers.base import BaseParser, Document

logger = get_logger(__name__)


class MarkdownParser(BaseParser):
    """Parses Markdown content, extracting H1 titles and preserving structural hierarchy."""

    def parse(self, raw_content: str, payload_id: str, payload_version: int, metadata: Dict[str, Any]) -> Document:
        lines = raw_content.splitlines()
        extracted_title = None

        # Look for top-level H1 heading (# Title)
        for line in lines:
            h1_match = re.match(r"^#\s+(.+)$", line.strip())
            if h1_match:
                extracted_title = h1_match.group(1).strip()
                break

        # Remove HTML tags if embedded in Markdown
        cleaned_text = re.sub(r"<[^>]+>", "", raw_content)

        # Normalize multiple consecutive empty lines
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

        title = extracted_title or metadata.get("filename", "Untitled Markdown Document")

        logger.debug("Parsed Markdown document", payload_id=payload_id, version=payload_version, title=title)
        return Document(
            payload_id=payload_id,
            payload_version=payload_version,
            cleaned_text=cleaned_text,
            title=title,
            metadata={**metadata, "parser": "MarkdownParser"}
        )