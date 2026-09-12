from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Canonical document-level metadata — the ground truth before chunking.

    Grouped into five concerns, mirrored onto every chunk at chunk time:

    * Lineage & storage      (doc_id, source_path, file_name, file_type,
                              content_hash, data_source)
    * Security & governance  (tenant_id, access_roles, classification)
    * Domain & taxonomy      (department, category, doc_type, domain, language)
    * Versioning & lifecycle (doc_version, status, created_at, updated_at,
                              effective_date)
    * Global context         (title, author, document_summary, total_pages)

    NOTE: the authored revision lives at ``doc_version``. ``version`` is a
    reserved vector-payload tag owned by the indexing pipeline (the
    indexed/rollback version, an int), so the two never collide.
    """

    # --- 1. Lineage & storage -----------------------------------------
    doc_id: str = Field(default="", description="Deterministic primary identifier")
    source_path: str = Field(default="", description="Storage locator (path / URI / S3 key)")
    file_name: str = Field(default="", example="AW-BIL-001.pdf")
    file_type: str = Field(default="", example=".pdf")
    content_hash: str = Field(
        default="", description="SHA-256 of the un-chunked document body"
    )
    data_source: str = Field(default="filesystem", description="Source modality")

    # --- 2. Security & governance -------------------------------------
    tenant_id: str = Field(default="default_tenant", description="Customer boundary")
    access_roles: List[str] = Field(
        default_factory=lambda: ["public"],
        description="Permitted roles, e.g. [\"billing_admin\", \"support_tier_2\"]",
    )
    classification: str = Field(
        default="internal",
        description="public | internal | confidential | restricted",
    )

    # --- 3. Domain & taxonomy ------------------------------------------
    department: str = Field(default="", example="billing")
    category: str = Field(default="", description="Grouping (e.g. sub-folder name)")
    doc_type: str = Field(default="document", example="policy")
    domain: Optional[str] = Field(default=None, example="wireless_telecom")
    language: str = Field(default="en", description="Primary ISO language code")

    # --- 4. Versioning & lifecycle -------------------------------------
    doc_version: str = Field(default="1.0", description="Authored revision / release tag")
    status: str = Field(default="active", description="draft | active | archived | deprecated")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    effective_date: Optional[str] = Field(default=None, example="2026-01-01")

    # --- 5. Global context ---------------------------------------------
    title: Optional[str] = Field(default=None, description="Original document title")
    author: Optional[str] = Field(default=None, description="Creator / accountable party")
    document_summary: Optional[str] = Field(
        default=None, description="LLM-generated summary of the entire file"
    )
    total_pages: Optional[int] = Field(default=None, ge=1)


class Document(BaseModel):
    """Raw document extracted from disk before chunking."""
    doc_id: str = Field(..., description="Unique identifier (e.g., file name)")
    content: str = Field(..., min_length=1, description="Extracted raw text")
    source: str = Field(..., description="Absolute or relative file path")
    data_source: str = Field(
        default="filesystem",
        description="Where the document came from (filesystem, rdbms, api, ...)",
    )
    metadata: DocumentMetadata = Field(
        default_factory=DocumentMetadata,
        description="Canonical document-level metadata (ground truth)",
    )


class SourceReference(BaseModel):
    """A discoverable unit inside a data source."""
    locator: str = Field(..., description="Path / URI / DSN identifying the content")
    doc_id: str = Field(..., description="Unique identifier (e.g., file name)")
    category: str = Field(default="", description="Grouping, e.g. sub-folder name")
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    data_source: str = Field(
        default="filesystem",
        description="Source modality (filesystem, rdbms, api, ...)",
    )


class TextChunk(BaseModel):
    """Processed text chunk ready for embedding."""
    chunk_id: str = Field(..., description="Unique identifier (doc_id_chunk_N)")
    doc_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., min_length=1, description="Chunked text slice")
    chunk_index: int = Field(..., ge=0, description="Sequential index")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Doc metadata inherited + chunk offsets"
    )


class EmbeddedChunk(BaseModel):
    """Vectorized chunk ready for database insertion."""
    chunk_id: str
    doc_id: str
    text: str
    embedding: List[float] = Field(..., description="Dense vector embedding")
    metadata: Dict[str, Any]