# Product Requirements Document (PRD)
## Versioned Retrieval-Augmented Generation (RAG) Platform

## 1. Overview
A modular, production-grade RAG pipeline system enabling document ingestion, versioned payload management, vector search, cross-encoder reranking, and automated quality evaluation. Designed for multi-tenant document search with soft-deletion and version tracking.

## 2. User Stories & Requirements

### 2.1 Document Ingestion
- **US-001**: As a developer, I can upload PDF, Markdown, and text documents through the web UI.
- **US-002**: As a developer, I can trigger ingestion pipelines that parse documents, split into chunks, and generate embedding vectors.
- **US-003**: As a developer, I need versioned payloads: new → v1, changed → vN+1 (deactivate old), unchanged → skip.
- **US-004**: As a developer, I need soft-deletion only: deleted payloads flagged `is_deleted=True`; chunks of deleted payloads flagged `is_purged=True`.

### 2.2 Retrieval & Search
- **US-005**: As a user, I can enter a natural language query and receive top-k relevant chunks.
- **US-006**: As a user, I can select query transformation modes: `rewrite` (normalize) or `hyde` (hypothetical document expansion).
- **US-007**: As a user, I can enable cross-encoder reranking with configurable `top_n` results.
- **US-008**: As a user, I need payload filtering: `is_active=True` and `is_deleted=False` to exclude soft-deleted entries.

### 2.3 Evaluation & Metrics
- **US-009**: As a developer, I can run quality benchmarks against a ground-truth dataset.
- **US-010**: As a developer, I need automated calculation of: Context Precision, Context Recall, Faithfulness, Mean Reciprocal Rank (MRR), Hit Rate, Answer Relevance.
- **US-011**: As a developer, I need console and JSON report export for CI/CD integration.

### 2.4 UI & Experience
- **US-012**: As a user, I need a Streamlit web interface with three pages: Search & Chat, Document Manager, Evaluation Dashboard.
- **US-013**: As a user, I need sidebar controls for transform mode, top_k, rerank top_n, and payload version filters.
- **US-014**: As a user, I need cited chunk visualization with version numbers and scores.

### 2.5 Non-Functional Requirements
- **Performance**: Vector search < 2s for top-5 results on PostgreSQL + pgvector.
- **Reliability**: Soft-deletion only; no hard deletes. All chunk dedup via SHA-256 hashing.
- **Extensibility**: New pipeline stages can be added via `PipelineStage[I, O]` base class. New metrics via `BaseMetric` subclass.
- **Observability**: Structured JSON logging via `structlog`. Metrics export for monitoring dashboards.

## 3. Acceptance Criteria
| ID | Criterion |
|----|-----------|
| AC-01 | `python main.py index --source-dir ./data/docs` successfully indexes documents and persists to PostgreSQL. |
| AC-02 | `python main.py query "question" --top-k 5` returns synthesized answer with cited chunks. |
| AC-03 | `python main.py evaluate --dataset ./evaluation/datasets/ground_truth.json` runs benchmark and displays mean metrics. |
| AC-04 | `python main.py ui` launches Streamlit with three navigable pages. |
| AC-05 | All 77 unit + integration tests pass without modification to `core/schemas.py`. |
| AC-06 | `sync_deleted_payloads(active_source_ids)` correctly flags `is_purged=True` on orphaned chunks. |

## 4. Dependencies
- Python 3.12+
- `sqlalchemy`, `psycopg2-binary`, `alembic`, `pydantic-settings`, `python-dotenv`
- `pypdf`, `structlog`, `rich`, `typer==0.15.4`
- `pytest>=9.1.1` (dev)
- PostgreSQL 16 with `pgvector` extension
- Qdrant vector store (Docker: `pgvector/pgvector:pg16`)

## 5. Development Notes
- `upsert_versioned_payload(payload)` handles v1 creation, vN+1 increments on content change, `UNCHANGED` skip.
- Chunk IDs format: `{payload_id}::v{payload_version}::c{chunk_index}`
- Embedding fallback uses `hashlib.md5(text).hexdigest()` → deterministic 1536-dim vectors when `OPENAI_API_KEY` unset.
- `sync_deleted_payloads(active_source_ids)` soft-deletes payloads missing from source scans and flags associated chunks for purge.
- Database: PostgreSQL 16 with `pgvector` extension (`pgvector/pgvector:pg16` container `ragops_postgres`).
- Credentials (via docker inspect): `ragops:ragops@localhost:5432/ragops`.