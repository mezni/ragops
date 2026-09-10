# Product Requirements Document — RAG Indexing Pipeline

## 1. Scope & Objectives

### 1.1 Purpose
Build a resilient, traceable RAG (Retrieval-Augmented Generation) document indexing pipeline that transforms raw filesystem documents into searchable vector embedments stored in PostgreSQL with pgvector.

### 1.2 Core objectives
- **Resilience**: Per-document transaction isolation — a single file failure never blocks the entire run
- **Traceability**: Every chunk carries lineage (source hash, parser version, cleaning applied, chunking strategy)
- **Configurability**: Embedding/enrichment providers resolved at runtime from Pydantic config, never hardcoded
- **Versioned index**: Support rollback via index version switching, not data rewrite
- **Cost & latency awareness**: Batch all external calls (embedding), skip redundant work on unchanged content

### 1.3 Out-of-scope (backlog)
- Advanced observability/dashboarding
- Postgres maintenance/tuning
- Streamlit UI exploitation
- LLM enrichment implementation (stubbed)
- Security hardening beyond basic secret env vars

## 2. Functional Requirements

### 2.1 Document ingestion
- Scan configured filesystem root recursively
- Calculate sha256 content hash (streamed, not full file in memory)
- Track size, mtime, status per file
- Classify each scan as: new, modified, or deleted (soft-delete, no physical removal)

### 2.2 Parsing (per-filetype)
- Text: extract raw text
- Markdown: extract heading hierarchy (`#`, `##`, etc.)
- PDF: extract text + page structure; heuristic for section headers via font properties
- Empty file → success with 0 chunks (not an error)
- Timeout per file to prevent single large PDF blocking the run

### 2.3 Cleaning pipeline (composable, named transformations)
| Transformation | Purpose |
|---|---|
| `normalize_whitespace` | Collapse spaces/tabs/newlines, strip leading/trailing |
| `dedupe_repeated_blocks` | Remove repeated headers/footers (PDF) |
| `normalize_unicode` | NFC normalization, remove control characters |
| `dedupe_exact_paragraphs` | Remove exact duplicate paragraphs within a document |

Each transformation returns `(cleaned_text, list_of_rules_applied)`. Stored in chunk metadata as `cleaning_applied`.

### 2.4 Chunking & lineage
- Configurable chunk size + overlap (overlap mitigates mid-sentence cuts)
- `ChunkMetadata` stores full provenance:
  - `document_id`, `document_hash`, `parser_version`
  - `cleaning_applied` (list[str])
  - `page_number` (PDF only)
  - `section_headers` (detected hierarchy)
  - `paragraph_index`, `char_start`, `char_end` (offsets in cleaned text)
  - `chunk_index`, `chunking_strategy`
  - `keywords`, `summary` (initially empty/`skipped`)
  - `enrichment_status` = `"skipped"` | `"pending"` | `"done"`

### 2.5 Embedding (configurable provider, batched)
- Provider resolved at runtime from config: `"openai"` | `"local"` | `"voyage"`
- Interface/abc with `embed(texts: list[str]) -> list[list[float]]`
- Factory pattern to instantiate provider without hardcoding
- Configurable batch size reduces API calls from N→1
- Retry/backoff on network errors / rate limits
- Dimension validated against active `index_versions.dimension` before write

### 2.6 Vector storage & versioning
- Table per dimension: `chunks_<dimension>` (e.g., `chunks_1536`)
- `index_versions` table tracks: provider, model, dimension, `is_active` flag
- Rollback = toggle `is_active` on a version, no data rewrite
- Before writing chunks for a modified document, delete its old chunks from the active version first

### 2.7 Pipeline runs & resilience
- Each document processed in its own DB transaction
- `StageFailure` caught per-document: document marked `status='failed'`, reason logged, run continues
- `pg_advisory_lock` prevents concurrent runs
- `pipeline_runs` table: `started_at`, `finished_at`, `status` (`running`/`success`/`partial_failure`/`failed`), `config_snapshot`, `stats` (jsonb: new/modified/deleted/failed/skipped)
- Run starts with `status='running'` and lock acquisition, stats incremented as documents process (not recalculated at end — survives mid-run crash)

### 2.8 Evaluations (separate from runs)
- `evaluations` table linked to `index_version_id` (not just run id)
- Fields: `query`, `expected_chunks`, `retrieved_chunks`, `metrics` (jsonb: precision@k, recall@k, MRR)
- Enables comparison between index versions for rollback decisions
- Golden query set versioned in repo, not in base

### 2.9 Migrations
- Alembic-managed
- Initial migration: `CREATE EXTENSION IF NOT EXISTS vector;`
- New embedding dimension → dynamic table creation via `SchemaManager` (not a static Alembic migration), under `pg_advisory_lock`
- Schema changes go through versioned migrations + schema manager for runtime-dimension tables

### 2.10 Docker containerization
- `docker-compose.yml`:
  - `postgres` service: `pgvector/pgvector:pg16`
  - `app` service: pipeline image
  - Source documents volume: mounted read-only at `/data/source`
  - Secrets (API keys) via `.env`
- Package manager: `uv` (replaces pip/poetry for dependency management and project operations)
- Health check: `SELECT 1` via `core/db.py`

## 3. Non-Functional Requirements

### 3.1 Performance
- Batching for embedding calls (configurable batch size)
- Streaming hash computation (never full file in memory)
- Per-document transactions avoid lock contention
- `pgvector` HNSW index created after initial bulk insert, not during

### 3.2 Observability
- Structured JSON logging per stage (start, completion, duration, errors)
- One log line per event — easy to pipe to any log collector
- Current state: local stdout only (no aggregation/dashboard — backlog item)

### 3.3 Maintainability
- All external-integrations behind protocols/interfaces + factories
- New parser/enrichment/embedding provider: implement interface, register in factory, enable via config — no code changes to pipeline core
- Clear amendment process for constitution (explicit decisions, not accidents)

### 3.4 Security
- API keys via Docker/.env secrets, never checked into repo
- Filesystem source mounted read-only
- Size/time limits per file to detect incomplete writes
- No physical deletion of indexed documents

## 4. Amendment Process
- Constitution amendments are explicit decisions with dates and justifications
- Never accidental consequences of implementation choices
- Current: no amendments
