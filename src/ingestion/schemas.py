from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataLineageMetadata(BaseModel):
    """Audit-grade record of how a chunk was produced.

    Composed at the vector-store boundary from the loader's source facts,
    the chunker's content fingerprints and the embedder's model provenance.
    Chroma requires *flat* string/scalar metadata, so the pipeline stores the
    individual fields (documented in :class:`ChunkMetadata`) and builds this
    model for JSON/audit exports via ``ChunkMetadata.lineage()``.

    Stages:
      Source system  -> storage_uri / raw_file_hash
      Ingestion job  -> ingestion_job_id / pipeline_version / parser_engine / ingested_at
      Chunker        -> parsed_text_hash / chunk_hash
      Embedder       -> embedding_model / embedding_dimensions / distance_metric / tokenizer_name
    """

    source_system: str = Field(default="filesystem", example="sharepoint")
    storage_uri: str = Field(default="", example="s3://rag-docs/billing/AW-BIL-001.pdf")
    external_id: Optional[str] = Field(default=None, example="page_948271")

    raw_file_hash: str = Field(default="", description="SHA-256 of the file bytes")
    parsed_text_hash: str = Field(
        default="", description="SHA-256 of cleaned, extracted body text"
    )
    chunk_hash: str = Field(default="", description="SHA-256 of this chunk's text")

    ingestion_job_id: str = Field(default="", example="job_uuid_9812a")
    pipeline_version: str = Field(default="", example="v0.3.0")
    parser_engine: str = Field(default="", example="PDFParser@pdfplumber-0.11")
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    embedding_model: str = Field(default="", example="openai/text-embedding-3-small")
    embedding_dimensions: int = Field(default=0, example=1536)
    distance_metric: str = Field(default="cosine")
    tokenizer_name: str = Field(default="cl100k_base")


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
    data_source: str = Field(default="filesystem", description="Source modality")
    content_hash: str = Field(
        default="", description="SHA-256 of the cleaned document body (parsed text hash)"
    )
    # --- Audit lineage facts -------------------------------------------
    raw_file_hash: str = Field(default="", description="SHA-256 of the file bytes")
    source_system: str = Field(default="filesystem", description="Origin platform")
    external_id: Optional[str] = Field(default=None, example="page_948271")
    parser_engine: str = Field(default="", example="PDFParser@pdfplumber-0.11")
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

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


class ChunkMetadata(BaseModel):
    """Structured chunk-level metadata — the compact view a retrieved chunk
    carries into generation, filtering, access control and the UI.

    Mirrors :class:`DocumentMetadata`'s grouping but is chunk-scoped. Four
    concerns:

    * Lineage & provenance   (doc_id, source_path, data_source, file_name,
                              file_type, content_hash, char_start/char_end,
                              page_number)
    * Context & hierarchy    (chunk_index, total_chunks, header_path, summary)
    * Filtering & governance (tenant_id, access_roles, classification, category,
                              department, doc_type, domain, language, status,
                              doc_version)
    * Versioning payload     (version, is_active, last_updated)

    ``content_hash`` is the SHA-256 of THIS chunk's text (idempotent chunk
    updates / deleted-modified-chunk tracking). ``version`` is the pipeline-
    owned indexed/rollback tag (int) — the authored revision lives at
    ``doc_version``.
    """

    # --- 1. Lineage & char-level provenance -----------------------------
    doc_id: str = Field(..., description="Root document identifier")
    source_path: str = Field(..., description="Original file path or URL")
    source: str = Field(..., description="Locator for re-loading the document")
    file_name: str = Field(default="", example="AW-BIL-001.pdf")
    file_type: str = Field(default="", example=".pdf")
    data_source: str = Field(default="filesystem", description="Source modality")
    content_hash: str = Field(
        ..., description="SHA-256 of this chunk's text, for idempotency"
    )
    char_start: int = Field(default=0, ge=0, description="Offset in raw document")
    char_end: int = Field(default=0, ge=0, description="Offset in raw document")
    page_number: Optional[int] = Field(default=None, ge=1)

    # --- 2. Context & hierarchy (parent/child + injection) ---------------
    chunk_index: int = Field(..., ge=0, description="Order within the document")
    total_chunks: int = Field(..., ge=1)
    header_path: str = Field(
        default="",
        description='Section breadcrumb, e.g. "Billing Policy > Refunds"',
    )
    summary: Optional[str] = Field(
        default=None, description="1-sentence LLM summary, reserved for enrichment"
    )

    # --- 3. Filtering & governance ---------------------------------------
    tenant_id: str = Field(default="default_tenant", description="Customer boundary")
    access_roles: List[str] = Field(
        default_factory=lambda: ["public"],
        description="Permitted roles, e.g. [\"billing_admin\", \"support_tier_2\"]",
    )
    classification: str = Field(
        default="internal",
        description="public | internal | confidential | restricted",
    )
    category: str = Field(default="", description="High-level filter, e.g. 'billing'")
    department: str = Field(default="")
    doc_type: str = Field(default="document")
    domain: Optional[str] = Field(default=None)
    language: str = Field(default="en", description="ISO language code")
    status: str = Field(default="active", description="draft | active | archived | deprecated")
    doc_version: str = Field(default="1.0", description="Authored revision tag")

    # --- 4. Versioning payload (pipeline-owned tags) ---------------------
    version: int = Field(default=0, description="Indexed/rollback version")
    is_active: bool = Field(default=True)
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp for the document's last change",
    )

    # --- 5. Audit lineage (chunk-level + provenance stamps) --------------
    raw_file_hash: str = Field(default="", description="SHA-256 of the file bytes")
    doc_content_hash: str = Field(
        default="", description="Parsed-text hash of the parent document"
    )
    parser_engine: str = Field(default="", example="PDFParser@pdfplumber-0.11")
    ingested_at: str = Field(default="", description="ISO timestamp of extraction")
    ingestion_job_id: str = Field(default="", example="job_uuid_9812a")
    pipeline_version: str = Field(default="", example="v0.3.0")
    embedding_model: str = Field(default="", example="openai/text-embedding-3-small")
    embedding_dimensions: int = Field(default=0, ge=0)
    distance_metric: str = Field(default="cosine")
    tokenizer_name: str = Field(default="cl100k_base")

    def lineage(self) -> DataLineageMetadata:
        """Assembles the audit record for this chunk (JSON/export view)."""
        return DataLineageMetadata(
            source_system=self.data_source,
            storage_uri=self.source_path,
            external_id=None,
            raw_file_hash=self.raw_file_hash,
            parsed_text_hash=self.doc_content_hash,
            chunk_hash=self.content_hash,
            ingestion_job_id=self.ingestion_job_id,
            pipeline_version=self.pipeline_version,
            parser_engine=self.parser_engine,
            ingested_at=self.ingested_at,
            embedding_model=self.embedding_model,
            embedding_dimensions=self.embedding_dimensions,
            distance_metric=self.distance_metric,
            tokenizer_name=self.tokenizer_name,
        )


class TextChunk(BaseModel):
    """Processed text chunk ready for embedding."""
    chunk_id: str = Field(..., description="Unique identifier (doc_id_chunk_N)")
    doc_id: str = Field(..., description="Parent document ID")
    text: str = Field(..., min_length=1, description="Chunked text slice")
    chunk_index: int = Field(..., ge=0, description="Sequential index")
    metadata: ChunkMetadata = Field(
        default_factory=ChunkMetadata,
        description="Structured doc metadata + chunk offsets give context & filters",
    )


class EmbeddedChunk(BaseModel):
    """Vectorized chunk ready for database insertion."""
    chunk_id: str
    doc_id: str
    text: str
    embedding: List[float] = Field(..., description="Dense vector embedding")
    metadata: Dict[str, Any]