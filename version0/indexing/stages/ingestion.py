"""
indexing/stages/ingestion.py
Ingestion stage responsible for payload version sync and format parsing.
"""

from typing import Any, Dict, List

from core.database import DatabaseManager, DocumentModel
from core.logging import get_logger
from core.pipeline import PipelineStage
from loaders.base import RawPayload
from parsers.base import BaseParser, Document
from parsers.markdown import MarkdownParser
from parsers.pdf import PDFParser
from parsers.text import TextParser

logger = get_logger(__name__)


class IngestionStage(PipelineStage[List[RawPayload], List[Document]]):
    """
    Ingests raw payloads, performs version resolution against PostgreSQL,
    parses raw content into clean Documents, and records document records.
    """

    def __init__(self, stage_name: str = "IngestionStage"):
        super().__init__(stage_name=stage_name)
        self.parsers: Dict[str, BaseParser] = {
            "application/pdf": PDFParser(),
            "text/markdown": MarkdownParser(),
            "text/x-markdown": MarkdownParser(),
            "text/plain": TextParser(),
        }
        self.default_parser = TextParser()

    def execute(self, input_data: List[RawPayload], context: Dict[str, Any]) -> List[Document]:
        db_manager: DatabaseManager = context["db_manager"]
        parsed_documents: List[Document] = []
        active_payload_ids: List[str] = []

        with db_manager.SessionLocal() as session:
            for raw_payload in input_data:
                active_payload_ids.append(raw_payload.payload_id)

                # 1. Sync payload state with database (handles SHA-256 hash check and versioning)
                payload_model, status = db_manager.upsert_versioned_payload(raw_payload)

                # Skip unchanged payloads if active version already exists
                if status == "UNCHANGED":
                    logger.info("Skipping parsing for unchanged payload", payload_id=raw_payload.payload_id)
                    continue

                # 2. Select appropriate parser based on content_type or file extension
                parser = self.parsers.get(raw_payload.content_type, self.default_parser)
                if raw_payload.payload_id.endswith(".md") and not isinstance(parser, MarkdownParser):
                    parser = self.parsers["text/markdown"]
                elif raw_payload.payload_id.endswith(".pdf") and not isinstance(parser, PDFParser):
                    parser = self.parsers["application/pdf"]

                # 3. Parse raw content into clean Document model
                parsed_doc = parser.parse(
                    raw_content=raw_payload.raw_content,
                    payload_id=payload_model.payload_id,
                    payload_version=payload_model.version,
                    metadata=raw_payload.metadata,
                )

                # 4. Save parsed Document entity to relational store
                doc_record = DocumentModel(
                    payload_id=parsed_doc.payload_id,
                    payload_version=parsed_doc.payload_version,
                    title=parsed_doc.title,
                    cleaned_text=parsed_doc.cleaned_text,
                )
                session.add(doc_record)
                parsed_documents.append(parsed_doc)

            session.commit()

        # 5. Soft-delete missing documents not present in current source scan
        db_manager.sync_deleted_payloads(active_source_ids=active_payload_ids)

        logger.info("Ingestion stage completed", new_or_updated_docs=len(parsed_documents))
        return parsed_documents