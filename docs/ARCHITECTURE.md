# Architecture — RAG Indexing Pipeline

## 1. Overview

```
┌─────────────┐    ┌──────────────┐    ┌────────┐    ┌───────┐    ┌────────┐    ┌─────────┐    ┌──────────────┐
│  Scanner    │ →  │  Change      │ →  │ Parse  │ →  │ Clean │ →  │ Chunk  │ →  │ Enrich  │ →  │ Embed        │
│ (filesystem)│    │  detection   │    │        │    │       │    │+lineage│    │(optional)   │(config runtime)
└─────────────┘    └──────────────┘    └────────┘    └───────┘    └────────┘    └─────────┘    └──────┬───────┘
                                                                                                        ↓
                                                                                              ┌───────────────────┐
                                                                                              │ Write pgvector     │
                                                                                              │ (versionned)       │
                                                                                              └───────────────────┘
```

Orchestration: cron → CLI. Every document traverses the full pipeline in a single logical transaction (see §5 Resilience).

---

## 2. Components & responsibilities

| Component | Responsibility | Depends on |
|---|---|---|
| `Scanner` | List files, calculate hash/size/mtime | filesystem |
| `ChangeDetector` | Compare scan vs `documents`, classify new/modified/deleted | `Scanner`, DB |
| `Parser` (registry by type) | Extract raw text + structure (pages, fonts) | source file |
| `Cleaner` (pipeline of transformations) | Normalize text, remove duplicates | `Parser` output |
| `Chunker` | Split cleaned text, produce `ChunkMetadata` | `Cleaner` output |
| `Enricher` (interface, `NoOpEnricher` default) | Keywords, summary — optional | `Chunker` output |
| `Embedder` (interface, resolved by config) | Vectorize chunks, by batch | `Enricher` output |
| `VectorStore` | Write to active version's chunks table | `Embedder` output |
| `RunTracker` | Create/update `pipeline_runs` entry | whole pipeline |
| `Evaluator` (independent of indexing run) | Execute query set, calculate metrics | `VectorStore` |

---

## 2bis. Detail of each stage

### Scanner
- Input: source root path (config). Output: list of `FileRecord(path, size, mtime, hash)`.
- Recursive traversal, sha256 hash computed in streaming (never full file in memory).
- Filter by allowed extensions (config).
- Attention points: files being written (verify mtime/stability between two close reads), symbolic links (follow or ignore — configurable), insufficient permissions (log and skip without failing the whole run).

### ChangeDetector
- Input: `Scanner` result + `documents` state. Output: three lists — `new`, `modified`, `deleted`.
- Single query to load all active indexed documents by `path`, then diff in memory.
- Attention point: rename is seen as delete + new (no content similarity detection yet — future feature).

### Parser
- Input: path + detected type (extension). Output: `ParsedDocument(text, structure_hints)` — structure hints = pages with font properties (PDF) or title hierarchy (Markdown).
- Dynamic registry `{extension: ParserImpl}`; each implementation isolates its own errors.
- Attention points: empty file → success with 0 chunks (not failure); PDF without text layer → known limitation (no OCR in v1, to document); configurable timeout per file to prevent a 500-page PDF blocking the whole run.

### Cleaner
- Input: raw text. Output: cleaned text + list of rules applied.
- Chain of pure, independently testable functions; fixed and documented order (e.g. dedup repeated blocks before whitespace normalization, to avoid biasing position-based detection).
- Attention point: over-aggressive dedup may remove legitimate repetitions (tables, refrains) — keep configurable similarity threshold.

### Chunker
- Input: cleaned text + `structure_hints`. Output: list of `Chunk(text, metadata: ChunkMetadata)`.
- Configurable strategy (fixed size + overlap at start). `section_headers` propagated from last detected title before each chunk.
- Attention points: overlap to mitigate mid-sentence cuts; a document smaller than a chunk produces exactly one chunk, never an error.

### Enricher
- Input: chunk text. Output: `EnrichmentResult(keywords, summary)`.
- `NoOpEnricher` default; future LLM implementation uses cache by `(document_hash, chunk_index, enrichment_version)`.
- Attention point: LLM call timeout or error must never fail the whole document — degrade to `enrichment_status="skipped"` with log, rattrapable via backfill.

### Embedder
- Input: list of texts. Output: list of vectors, batched per `embedding.batch_size`, with retry/backoff on network errors or rate-limits.
- Attention point: returned dimension must be validated against `index_versions.dimension` before write — a provider that silently changes default model must never pass unnoticed.

### VectorStore (write)
- Input: document, chunks, embeddings, active version. Output: rows inserted in chunks table.
- Active version resolved once at run start, not per chunk. Batch insert, not row-by-row.
- Attention point: for a modified document, its old chunks in the active version must be deleted before re-insertion — otherwise stale chunks remain searchable.

### RunTracker
- Input: run events. Output: `pipeline_runs` row kept up-to-date.
- Created `status='running'` at start (lock taken), stats incremented as documents process — not recalculated at end, to stay correct even if the process crashes mid-route.

### Evaluator
- Input: query set + active index version. Output: `evaluations` rows + aggregated metrics.
- Executed on demand, independently of an indexing run.
- Attention point: golden query set must be versioned in repo (not in base) to stay comparable over time.

---

## 3. Repository layout

```
rag-indexer/
├── pipeline/
│   ├── config.py               # PipelineConfig (Pydantic), YAML/env loading
│   ├── cli.py                  # `python -m pipeline.run`, `pipeline enrich --backfill`
│   ├── core/
│   │   ├── stage.py             # Protocol Stage
│   │   ├── context.py           # PipelineContext
│   │   ├── pipeline.py          # Pipeline, StageFailure, build_document_pipeline
│   │   ├── logging.py           # configuration + structured logging helpers
│   │   └── db.py                # SQLAlchemy engine, pool, session factory
│   ├── indexing/
│   │   ├── scanner/
│   │   │   └── filesystem.py
│   │   ├── change_detection/
│   │   │   └── detector.py
│   │   ├── parsers/
│   │   │   ├── base.py          # Protocol Parser
│   │   │   ├── pdf.py
│   │   │   ├── text.py
│   │   │   └── markdown.py
│   │   ├── cleaning/
│   │   │   ├── base.py          # Protocol Cleaner, composable pipeline
│   │   │   ├── whitespace.py
│   │   │   ├── dedupe.py
│   │   │   └── unicode.py
│   │   ├── chunking/
│   │   │   ├── base.py          # Protocol Chunker
│   │   │   └── recursive_char.py
│   │   ├── enrichment/
│   │   │   ├── base.py          # Protocol Enricher
│   │   │   ├── noop.py
│   │   │   └── llm.py           # future implementation
│   │   ├── embedding/
│   │   │   ├── base.py          # Protocol Embedder
│   │   │   ├── openai_provider.py
│   │   │   ├── local_provider.py
│   │   │   └── factory.py
│   │   ├── storage/
│   │       ├── models.py        # ORM tables
│   │       ├── vector_store.py
│   │       ├── run_tracker.py
│   │       └── schema_manager.py # dynamic chunks_<dimension> creation
│   ├── evaluation/
│   │   └── evaluator.py         # independent of indexing, reads active version
│   └── models/
│       └── metadata.py          # ChunkMetadata (Pydantic)
├── migrations/                  # Alembic
├── tests/
│   ├── unit/                    # per-component mirror directory
│   ├── golden/                  # end-to-end expected results
│   └── integration/
├── streamlit_app/               # future — ops dashboard
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── config.yaml
└── .env
```

`core/` holds what is transverse to the whole pipeline (execution abstraction, logging). `indexing/` holds the indexation-specific bricks — each remains an independent module, agnostic of being called by a `Stage` or tested alone.

---

## 4. Data model

```sql
-- Tracked documents from the filesystem
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path            TEXT NOT NULL UNIQUE,
    content_hash    TEXT NOT NULL,
    size            BIGINT NOT NULL,
    mtime           TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('active', 'deleted', 'failed')),
    failure_reason  TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each pipeline run
CREATE TABLE pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial_failure', 'failed')),
    config_snapshot JSONB NOT NULL,
    stats           JSONB
);

-- Vector index versions (enables rollback)
CREATE TABLE index_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding_provider  TEXT NOT NULL,
    embedding_model     TEXT NOT NULL,
    dimension           INT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active           BOOLEAN NOT NULL DEFAULT false
);

-- Chunks table per embedding dimension (see constitution, Article IV)
-- Dynamic name: chunks_<dimension>, e.g. chunks_1536
CREATE TABLE chunks_1536 (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id),
    index_version_id    UUID NOT NULL REFERENCES index_versions(id),
    chunk_text          TEXT NOT NULL,
    embedding           VECTOR(1536) NOT NULL,
    metadata            JSONB NOT NULL   -- serialized ChunkMetadata
);

-- Evaluations, attached to an index version (not just a run)
CREATE TABLE evaluations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    index_version_id    UUID NOT NULL REFERENCES index_versions(id),
    query               TEXT NOT NULL,
    expected_chunks     JSONB NOT NULL,
    retrieved_chunks    JSONB NOT NULL,
    metrics             JSONB NOT NULL,  -- precision@k, recall@k, MRR
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes to create after initial fill (not before, for bulk insert performance):
```sql
CREATE INDEX ON chunks_1536 USING hnsw (embedding vector_cosine_ops);
```

---

## 4bis. Chunk metadata (`ChunkMetadata`)

Serialized in the `metadata` (JSONB) column of `chunks_<dimension>`. This is the lineage contract: everything needed to reconstruct about a chunk without going back to the source file.

```python
class ChunkMetadata(BaseModel):
    document_id: UUID
    document_hash: str             # hash of source file at chunking time
    parser_version: str            # detects chunks to re-parser after parser upgrade
    cleaning_applied: list[str]    # cleaning rules actually applied
    page_number: int | None        # PDF only
    section_headers: list[str]     # detected hierarchy, e.g. ["Chapter 2", "2.1 Installation"]
    paragraph_index: int
    char_start: int                # offsets on cleaned text (not raw)
    char_end: int
    chunk_index: int               # chunk position within the document
    chunking_strategy: str         # e.g. "recursive_char_v1"

    # Enrichment — optional, see Enricher/NoOpEnricher
    keywords: list[str] = []
    summary: str | None = None
    enrichment_status: Literal["skipped", "pending", "done"] = "skipped"
    enrichment_provider: str | None = None
    enrichment_version: str | None = None
```

Associated rules (constitution, Article I):
- `document_hash` + `parser_version` allow detecting a stale chunk without comparing content.
- `char_start`/`char_end` are relative to cleaned text, to stay consistent with what was actually chunked.
- `enrichment_status="skipped"` (not an empty field) explicitly distinguishes "never treated" from "treated, found nothing" — necessary for future backfill.

---

## 5. Key interfaces (stable contracts)

```python
class Parser(Protocol):
    def parse(self, file_path: Path) -> ParsedDocument: ...

class Cleaner(Protocol):
    def clean(self, text: str) -> tuple[str, list[str]]: ...  # (text, rules applied)

class Chunker(Protocol):
    def chunk(self, cleaned_text: str, doc_context: DocumentContext) -> list[Chunk]: ...

class Enricher(Protocol):
    def enrich(self, chunk_text: str) -> EnrichmentResult: ...

class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Each interface has factory-based resolution from `PipelineConfig`, never hardcoded instantiation in business logic (constitution, Article II).

---

## 6. Execution by stages (`Pipeline`)

Document processing is not a monolithic function: it's a `Pipeline` built by adding `Stage` one by one. Each stage is coded and tested in isolation, before being hooked to the rest.

### Stage contract

```python
class Stage(Protocol):
    name: str
    def run(self, context: "PipelineContext") -> "PipelineContext": ...
```

### Context carried between stages

```python
class PipelineContext(BaseModel):
    document: DocumentRecord
    raw_text: str | None = None
    cleaned_text: str | None = None
    cleaning_applied: list[str] = []
    chunks: list[Chunk] = []
    embeddings: list[list[float]] = []
    stage_history: list[str] = []   # trace of already-passed stages, for debug

    class Config:
        arbitrary_types_allowed = True
```

### The pipeline — assembled incrementally, with per-stage structured logging

```python
import logging
import time

logger = logging.getLogger("pipeline")

class StageFailure(Exception):
    def __init__(self, stage_name: str, context: "PipelineContext", cause: Exception):
        self.stage_name = stage_name
        self.context = context
        super().__init__(f"{stage_name} failed: {cause}")

class Pipeline:
    def __init__(self) -> None:
        self._stages: list[Stage] = []

    def add_stage(self, stage: Stage) -> "Pipeline":
        self._stages.append(stage)
        return self

    def run(self, context: PipelineContext) -> PipelineContext:
        for stage in self._stages:
            start = time.monotonic()
            log_ctx = {"stage": stage.name, "document_id": str(context.document.id)}
            logger.info("stage_started", extra=log_ctx)
            try:
                context = stage.run(context)
                context.stage_history.append(stage.name)
                logger.info("stage_completed", extra={
                    **log_ctx,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                })
            except Exception as e:
                logger.error("stage_failed", extra=log_ctx, exc_info=True)
                raise StageFailure(stage.name, context, e) from e
        return context
```

### Config-driven construction (constitution, Article II — config decides once at build time, not dispersed across stages)

```python
def build_document_pipeline(config: PipelineConfig) -> Pipeline:
    pipeline = Pipeline().add_stage(ParseStage()).add_stage(CleanStage()).add_stage(ChunkStage())
    pipeline.add_stage(EnrichStage() if config.enrichment.enabled else NoOpEnrichStage())
    return pipeline.add_stage(EmbedStage()).add_stage(WriteStage())
```

### Per-document resilience (constitution, Article III) : pipeline executed per-document in isolated transaction, and a `StageFailure` marks the document as failed without stopping the run. `context.stage_history` indicates exactly how far the document got before failure.

```python
document_pipeline = build_document_pipeline(config)

for document in changed_documents:
    try:
        with transaction():
            context = document_pipeline.run(PipelineContext(document=document))
    except StageFailure as e:
        mark_failed(document, reason=str(e), last_stage=e.stage_name)
        continue  # the run proceeds to the next document
```

The entire run is wrapped in `pg_advisory_lock` to prevent concurrent execution.

---

## 7. Docker topology

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [pgdata:/var/lib/postgresql/data]
  app:
    build: ./docker
    depends_on: [postgres]
    volumes:
      - ./source_documents:/data/source:ro
    env_file: .env
volumes:
  pgdata:
```

---

## 8. Database management

- **Connection**: single SQLAlchemy engine per process, with connection pool (`pool_size`, `max_overflow` configurable in `PipelineConfig`). Never open a connection manually outside this pool.
- **Sessions and transactions**: one session per document, opened at the start of its pipeline pass, committed at the end, automatic rollback on `StageFailure` (see §6). No shared session between documents.
- **Migrations**: Alembic, executed explicitly via `pipeline db upgrade` — never automatically at app start, to avoid concurrent deployments triggering two migrations in parallel.
- **Dynamic table creation**: a new embedding dimension does not go through a classic Alembic migration (dimension is only known at runtime, per chosen provider). A `SchemaManager` executes `CREATE TABLE IF NOT EXISTS chunks_<dimension> (...)` under a dedicated `pg_advisory_lock`, then records the new `index_version` — and logs this event just like a migration, for complete schema evolution traceability.
- **Health check**: `SELECT 1` exposed for Docker/orchestrator healthcheck, independent of the rest of the pipeline.

---

## 9. Foreseen extension points

- **New document source** (beyond filesystem): implement a new `Scanner`, the rest of the pipeline is unchanged.
- **New embedding/enrichment provider**: implement the interface, register in the factory, enable via config.
- **Streamlit dashboard** (backlog): reads directly `pipeline_runs`, `evaluations`, `index_versions` — no intermediate API needed for v1.
