import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from core.config import get_settings
from ingestion.parsers import get_parser
from ingestion.schemas import Document, DocumentMetadata, SourceReference
from utils.text_processing import clean_text


class DocumentLoader:
    """Loads raw files, strips HTML/markup, and builds the canonical
    :class:`DocumentMetadata` record. Output: Document."""

    @staticmethod
    def extract_frontmatter(text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extracts key-value header metadata (e.g., Version, Last Updated,
        Status, Department) and strips it from the main body content.
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
            "doc_type": r"Doc Type\s*:\s*([A-Za-z]+)",
            "title": r"Title\s*:\s*(.+)",
            "author": r"(?:Author|Owner)\s*:\s*(.+)",
            "effective_date": r"Effective Date\s*:\s*([\d-]+)",
            "classification": r"Classification\s*:\s*([A-Za-z]+)",
            "tenant_id": r"Tenant ID\s*:\s*([A-Za-z0-9_-]+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted_meta[key] = match.group(1).strip()
                # Remove matched key-value string from core text
                text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        return text.strip(), extracted_meta

    def _build_metadata(
        self,
        file_path: Path,
        content_hash: str,
        meta: Dict[str, Any],
    ) -> DocumentMetadata:
        """Merges frontmatter, filesystem facts and centralized defaults
        (tenancy/taxonomy) into the canonical document metadata record."""
        cfg = get_settings().metadata

        mtime = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        category = file_path.parent.name
        department = meta.get("department") or category

        return DocumentMetadata(
            doc_id=file_path.stem,
            source_path=str(file_path),
            file_name=file_path.name,
            file_type=file_path.suffix.lower(),
            content_hash=content_hash,
            data_source="filesystem",
            # Security & governance (centralized defaults).
            tenant_id=meta.get("tenant_id") or cfg.tenant_id,
            access_roles=list(cfg.access_roles),
            classification=meta.get("classification") or cfg.classification,
            # Domain & taxonomy.
            department=department,
            category=category,
            doc_type=meta.get("doc_type") or cfg.doc_type,
            domain=cfg.domain,
            language=cfg.language,
            # Versioning & lifecycle.
            doc_version=meta.get("doc_version") or "1.0",
            status=meta.get("status") or "active",
            created_at=mtime,
            updated_at=mtime,
            effective_date=meta.get("effective_date"),
            # Global context.
            title=meta.get("title"),
            author=meta.get("author"),
            document_summary=None,  # reserved for LLM enrichment
        )

    def run(self, file_path: Path) -> Document:
        """Reads any supported file format, cleans content, and constructs a
        Document. Parsing is delegated to the parser registered for the
        file's extension (PDF, Markdown, plain text, ...)."""
        if not file_path.exists():
            raise FileNotFoundError(f"Target document not found: {file_path}")

        # 1. Parse raw text via the format-specific parser
        parser = get_parser(file_path)
        raw_text = parser.extract(file_path)

        if not raw_text.strip():
            raise ValueError(f"Extracted content is empty for file: {file_path}")

        # Content digest to power idempotent deduplication downstream
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        # 2. Clean HTML & extract administrative frontmatter
        sanitized_text = clean_text(raw_text)
        body_text, extracted_meta = self.extract_frontmatter(sanitized_text)

        # 3. Canonical document metadata + physical page count (when known)
        metadata = self._build_metadata(file_path, content_hash, extracted_meta)
        total_pages = parser.page_count(file_path)
        if total_pages is not None:
            metadata = metadata.model_copy(
                update={"total_pages": total_pages}
            )

        return Document(
            doc_id=file_path.stem,
            content=body_text,
            source=str(file_path),
            data_source="filesystem",
            metadata=metadata,
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
                "metadata": doc.metadata.model_copy(
                    update={
                        "doc_id": ref.doc_id,
                        "category": ref.category,
                        "data_source": ref.data_source,
                        "source_path": ref.locator,
                        "file_name": ref.file_name or doc.metadata.file_name,
                        "file_type": ref.file_type or doc.metadata.file_type,
                    }
                ),
            }
        )


# Backward-compatible alias (legacy name from the single-file stage refactor)
IngestionStage = DocumentLoader