from typing import Any, Dict
from core.logging import get_logger
from parsers.base import BaseParser, Document

logger = get_logger(__name__)


class TextParser(BaseParser):
    """Parses plain text content with basic whitespace normalization."""

    def parse(self, raw_content: str, payload_id: str, payload_version: int, metadata: Dict[str, Any]) -> Document:
        # Normalize newline character representations and remove excessive blank lines
        lines = [line.strip() for line in raw_content.splitlines()]
        non_empty_lines = [line for line in lines if line]
        
        # Infer title from the first non-empty line if short enough
        title = None
        if non_empty_lines and len(non_empty_lines[0]) <= 100:
            title = non_empty_lines[0]

        cleaned_text = "\n".join(non_empty_lines)

        logger.debug("Parsed plain text content", payload_id=payload_id, version=payload_version)
        return Document(
            payload_id=payload_id,
            payload_version=payload_version,
            cleaned_text=cleaned_text,
            title=title or metadata.get("filename", "Untitled Document"),
            metadata=metadata
        )