import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Tuple

from ingestion.parsers import get_parser
from ingestion.schemas import Document, SourceReference
from utils.text_processing import clean_text


class DocumentLoader:
    """Loads raw files, strips HTML/markup, and extracts administrative
    frontmatter into metadata. Output: Document."""

    @staticmethod
    def extract_frontmatter(text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts key-value header metadata (e.g., Version, Last Updated, Status)
        and strips it from the main body content.
        """
        extracted_meta = {}

        # Regex patterns to capture administrative header blocks.
        # "version" is a reserved payload tag (indexed/rollback version),
        # so the document's authored version is stored as "doc_version".
        patterns = {
            "document_id": r"Document ID\s*:\s*([A-Z0-9-]+)",
            "doc_version": r"Version\s*:\s*([\d.]+)",
            "department": r"Department\s*:\s*([A-Za-z]+)",
            "last_updated": r"Last Updated\s*:\s*([\d-]+)",
            "status": r"Status\s*:\s*([A-Za-z]+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_meta[key] = match.group(1).strip()
                # Remove matched key-value string from core text
                text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip(), extracted_meta

    def run(self, file_path: Path) -> Document:
        """Reads any supported file format, cleans content, and constructs a
        Document. Parsing is delegated to the parser registered for the
        file's extension (PDF, Markdown, plain text, ...)."""
        if not file_path.exists():
            raise FileNotFoundError(f"Target document not found: {file_path}")

        # 1. Parse raw text via the format-specific parser
        raw_text = get_parser(file_path).extract(file_path)

        if not raw_text.strip():
            raise ValueError(f"Extracted content is empty for file: {file_path}")

        # Content digest to power idempotent deduplication downstream
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        # 2. Clean HTML & extract administrative frontmatter
        sanitized_text = clean_text(raw_text)
        body_text, extracted_meta = self.extract_frontmatter(sanitized_text)

        return Document(
            doc_id=file_path.stem,
            content=body_text,
            source=str(file_path),
            data_source="filesystem",
            metadata={
                "file_name": file_path.name,
                "file_type": file_path.suffix.lower(),
                "category": file_path.parent.name,  # Captures "billing" from path
                "data_source": "filesystem",
                "content_hash": content_hash,
                **extracted_meta,  # Saved into Chroma payload rather than chunk text
            }
        )

    def from_reference(self, ref: SourceReference) -> Document:
        """Loads a document from a source reference, stamping source metadata.

        Unlike :meth:`run`, category / doc_id / data_source come from the
        reference rather than being re-derived from the file path.
        """
        doc = self.run(Path(ref.locator))
        return doc.model_copy(
            update={
                "doc_id": ref.doc_id,
                "metadata": {
                    **doc.metadata,
                    "category": ref.category,
                    "data_source": ref.data_source,
                },
            }
        )


# Backward-compatible alias (legacy name from the single-file stage refactor)
IngestionStage = DocumentLoader