# Execution Plan — RAG Indexing Pipeline

Recommended implementation order, phase by phase. Each phase has a clear exit criteria before moving to the next. Reference: `constitution.md` (principles), `architecture.md` (detailed schema, including `Stage`/`Pipeline` §6), `brief.md` (functional summary).

---

## Phase 0 — Project scaffolding

**Goal**: have an executable skeleton, no business logic.

- [ ] Repository structure (`pipeline/core/`, `pipeline/indexing/`, `migrations/`, `tests/`, `docker/`)
- [ ] `docker-compose.yml` with `postgres` (image `pgvector/pgvector:pg16`) and `app`
- [ ] `PipelineConfig` (Pydantic) loaded from `config.yaml` + `.env`
- [ ] `core/db.py` : SQLAlchemy engine + connection pool, session factory (see `architecture.md` §8)
- [ ] Alembic initialized, migration 0: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] CLI command `pipeline db upgrade` — migrations executed explicitly, never at app start

**Exit criteria**: `docker-compose up` starts Postgres with pgvector active, `pipeline db upgrade` applies migrations without error, `SELECT 1` via `core/db.py` succeeds.

---

## Phase 1 — Ingestion & change detection

**Goal**: know which files changed since last run, without parsing yet.

- [ ] Migration: `documents` table
- [ ] `indexing/scanner/filesystem.py` : list files, compute `content_hash`/`size`/`mtime` (streamed, not all in memory)
- [ ] `indexing/change_detection/detector.py` : classify as new / modified / deleted by comparison with `documents`
- [ ] Minimal CLI: `pipeline scan` that displays detection result without writing anything else

**Exit criteria**: running `pipeline scan` twice on the same folder detects no changes; modifying a file makes it appear as "modified".

---

## Phase 2 — Parsing & cleaning

**Goal**: extract clean text from detected files.

- [ ] `indexing/parsers/` : `Parser` (Protocol) + `text`, `markdown`, `pdf` implementations — each isolates its own errors (empty file = success with 0 chunks, not failure)
- [ ] Basic structure extraction (PDF: pages + font properties; Markdown: `#`/`##` headers)
- [ ] `indexing/cleaning/` : composable pipeline (`normalize_whitespace`, `dedupe_repeated_blocks`, `normalize_unicode`, `dedupe_exact_paragraphs`), fixed order and documented
- [ ] Each transformation returns `(text, list_of_rules_applied)`
- [ ] `ParseStage` and `CleanStage` (see `architecture.md` §6) hooked to these implementations

**Exit criteria**: for each file type, a unit test verifies extracted text is clean and `cleaning_applied` reflects exactly the triggered rules.

---

## Phase 3 — Chunking & lineage metadata

**Goal**: split cleaned text into chunks carrying full traceability.

- [ ] `ChunkMetadata` (Pydantic, `models/metadata.py`) — all lineage fields (`architecture.md` §4bis)
- [ ] `indexing/chunking/` : `Chunker` (Protocol) + `recursive_char_v1` implementation, with overlap to mitigate mid-sentence cuts
- [ ] Header hierarchy detection (Markdown direct, PDF via font heuristic)
- [ ] Enrichment fields present but empty (`enrichment_status="skipped"`) — no LLM implementation yet
- [ ] `indexing/enrichment/noop.py` : `NoOpEnricher` hooked by default
- [ ] `ChunkStage` (see `architecture.md` §6) hooked to these implementations

**Exit criteria**: a test document produces chunks whose exact source position and applied transformations can be reconstituted from metadata alone.

---

## Phase 4 — Configurable & batched embedding

**Goal**: vectorize chunks via a runtime-chosen provider, never one call per chunk.

- [ ] `indexing/embedding/` : `Embedder` (Protocol) + at least two implementations (e.g. `openai`, `local`)
- [ ] `EmbedderFactory` resolving implementation from `PipelineConfig`
- [ ] Configurable batch size (in `config.yaml`), retry/backoff on network errors / rate-limits
- [ ] Returned dimension validated against `index_versions.dimension` before any write
- [ ] `EmbedStage` (see `architecture.md` §6) hooked to these implementations

**Exit criteria**: changing `embedding.provider` in config switches the used provider without code changes; a run on 100 chunks does not trigger 100 network calls.

---

## Phase 5 — Versioned vector storage

**Goal**: write embeddings in pgvector with functional rollback.

- [ ] Migration: `index_versions` table
- [ ] `indexing/storage/schema_manager.py` : dynamically creates `chunks_<dimension>` (`CREATE TABLE IF NOT EXISTS`, under dedicated `pg_advisory_lock`) when a new dimension is registered — not a static Alembic migration, see `architecture.md` §8
- [ ] `indexing/storage/vector_store.py` : `write()` resolves active version once per run, batch inserts, first deletes old chunks of a modified document from the active version
- [ ] `WriteStage` (see `architecture.md` §6) hooked to `vector_store.write()`
- [ ] Rollback command: toggle `is_active` to a previous version

**Exit criteria**: create a second index version (different provider/dimension), then rollback to the first, without data loss or error.

---

## Phase 6 — Resilience & run tracking

**Goal**: make the pipeline robust to partial failure and fully traceable end-to-end.

- [ ] `core/stage.py`, `core/context.py`, `core/pipeline.py` : `Stage`/`PipelineContext`/`Pipeline` abstraction (see `architecture.md` §6)
- [ ] `core/logging.py` : per-stage structured logging (start, completion, duration, errors) — see `architecture.md` §6
- [ ] `build_document_pipeline(config)` : assembles `ParseStage → CleanStage → ChunkStage → [Enrich|NoOpEnrich]Stage → EmbedStage → WriteStage` per config
- [ ] Migration: `pipeline_runs` table
- [ ] Pipeline execution per document in isolated transaction
- [ ] `StageFailure` caught: document marked failed, reason logged, last stage recorded, run continues
- [ ] `RunTracker` : creation/update of `pipeline_runs` entry (status, stats, `config_snapshot`)
- [ ] `pg_advisory_lock` to prevent concurrent runs

**Exit criteria**: inject a deliberately corrupt file into a batch — run ends in `partial_failure`, all other documents indexed, failure reason readable in `documents`.

---

## Phase 7 — Tests & CI

**Goal**: evolve the pipeline without silent regressions.

- [ ] Unit tests per step (`tests/unit/`) : parsers, cleaners, chunker
- [ ] Golden document set (`tests/golden/`) with reference result, end-to-end test
- [ ] CI pipeline: migrations → tests → Docker image build, on every push

**Exit criteria**: a pull request breaking any pipeline step fails CI before merge.

---

## Phase 8 — Evaluations

**Goal**: objectively measure retrieval quality of an index version.

- [ ] Migration: `evaluations` table
- [ ] `Evaluator`: executes a query set against an index version, calculates precision@k / recall@k / MRR
- [ ] CLI command: `pipeline evaluate --index-version <id>`

**Exit criteria**: comparing metrics of two index versions enables objective decision on which to activate.

---

## Backlog (out of scope)

Not planned in this plan, to re-evaluate once phases 0-8 are stable:
- Advanced observability (metrics, log aggregation, alerting) — basic per-stage structured logging already covered in Phase 6
- FinOps: cost tracking per run and per provider, budgets, alerting on overrun
- Performance & costs beyond batching (already in Phase 4): file-level parallelism with concurrency limit, cache by hash to never reprocess unchanged content
- Postgres/pgvector maintenance (index tuning, VACUUM/ANALYZE, backups)
- Streamlit dashboard (ops, rollback from UI)
- Security & config hardening (secrets, timeouts/size limits per file type)
- Real LLM enrichment implementation (keywords, summary) + backfill commandENDEOF
echo "PLAN.md created"
