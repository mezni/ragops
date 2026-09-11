from pathlib import Path
from typing import Any, Dict
from core.logging import get_logger
from parsers.base import BaseParser, Document

logger = get_logger(__name__)


class PDFParser(BaseParser):
    """Parses PDF documents from disk path or binary references."""

    def parse(self, raw_content: str, payload_id: str, payload_version: int, metadata: Dict[str, Any]) -> Document:
        file_path = Path(raw_content)
        
        # Check if raw_content contains a valid file path string
        if not file_path.exists() or not file_path.is_file():
            logger.error("PDF parser received invalid file path", path=raw_content)
            raise FileNotFoundError(f"PDF file not found for parsing: {raw_content}")

        extracted_pages = []
        page_count = 0

        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            page_count = len(reader.pages)

            for idx, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(page_text.strip())

        except ImportError:
            logger.warning("pypdf not installed. Falling back to basic file reading.")
            raise ImportError("pypdf package is required for PDF parsing. Install via `pip install pypdf`.")
        except Exception as e:
            logger.error("Error reading PDF file", file_path=str(file_path), error=str(e))
            raise e

        cleaned_text = "\n\n".join(extracted_pages)
        title = metadata.get("filename", file_path.stem)

        logger.debug("Parsed PDF document", payload_id=payload_id, pages=page_count)
        return Document(
            payload_id=payload_id,
            payload_version=payload_version,
            cleaned_text=cleaned_text,
            title=title,
            metadata={
                **metadata,
                "page_count": page_count,
                "parser": "PDFParser"
            }
        )