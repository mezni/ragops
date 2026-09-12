import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

from ingestion.schemas import Document
from utils.markdown import table_to_markdown
from utils.ocr import ocr_text
from utils.text_processing import clean_text

logger = logging.getLogger(__name__)


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

        # Regex patterns to capture administrative header blocks
        patterns = {
            "document_id": r"Document ID\s*:\s*([A-Z0-9-]+)",
            "version": r"Version\s*:\s*([\d.]+)",
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

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extracts text and Markdown-rendered tables from a PDF via pdfplumber.

        Falls back to OCR for scanned pages that have no embedded text.
        """
        page_parts: List[str] = []

        with pdfplumber.open(file_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                parts: List[str] = []

                page_text = page.extract_text() or ""
                if page_text:
                    parts.append(page_text)

                for table in page.extract_tables() or []:
                    table_md = table_to_markdown(table)
                    if table_md:
                        parts.append(table_md)

                content = "\n\n".join(parts)

                # Scanned page — no text layer, no tables: try OCR.
                if not content.strip():
                    ocr = ocr_text(file_path, page_number)
                    if ocr:
                        content = ocr

                if content.strip():
                    page_parts.append(content)

        return "\n\n".join(page_parts)

    def run(self, file_path: Path) -> Document:
        """Reads a .pdf or .txt file, cleans content, and constructs a Document."""
        if not file_path.exists():
            raise FileNotFoundError(f"Target document not found: {file_path}")

        raw_text = ""
        # 1. Extract raw text from file
        if file_path.suffix.lower() == ".pdf":
            raw_text = self._extract_pdf_text(file_path)
        elif file_path.suffix.lower() in [".txt", ".md"]:
            raw_text = file_path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

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
            metadata={
                "file_name": file_path.name,
                "file_type": file_path.suffix.lower(),
                "category": file_path.parent.name,  # Captures "billing" from path
                "content_hash": content_hash,
                **extracted_meta,  # Saved into Chroma payload rather than chunk text
            }
        )


# Backward-compatible alias (legacy name from the single-file stage refactor)
IngestionStage = DocumentLoader