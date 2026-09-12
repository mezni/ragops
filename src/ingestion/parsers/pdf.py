import logging
from pathlib import Path
from typing import List, Optional

import pdfplumber

from ingestion.parsers.base import DocumentParser
from utils.markdown import table_to_markdown
from utils.ocr import ocr_text

logger = logging.getLogger(__name__)


class PDFParser(DocumentParser):
    """Extracts text and Markdown-rendered tables from a PDF via pdfplumber.

    Falls back to OCR for scanned pages that have no embedded text layer.
    """

    extensions = (".pdf",)
    library_name = "pdfplumber"

    def page_count(self, path: Path) -> Optional[int]:
        """Physical page count, used for the document's ``total_pages``."""
        try:
            with pdfplumber.open(path) as pdf:
                return len(pdf.pages)
        except Exception:
            return None

    def extract(self, path: Path) -> str:
        page_parts: List[str] = []
        table_count = 0

        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                parts: List[str] = []

                page_text = page.extract_text() or ""
                if page_text:
                    parts.append(page_text)

                for table in page.extract_tables() or []:
                    table_md = table_to_markdown(table)
                    if table_md:
                        parts.append(table_md)
                        table_count += 1

                content = "\n\n".join(parts)

                # Scanned page — no text layer, no tables: try OCR.
                if not content.strip():
                    ocr = ocr_text(path, page_number)
                    if ocr:
                        content = ocr

                if content.strip():
                    page_parts.append(content)

        logger.debug(
            "PDFParser extracted %d pages / %d tables from %s",
            len(page_parts),
            table_count,
            path,
        )
        return "\n\n".join(page_parts)