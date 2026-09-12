# Changelog — RAG Indexing Pipeline

All notable changes to this project are documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project aligns with the phases defined in `execution_plan.md`.

## [Unreleased]

### Planned
- Filesystem change detection (Step 1.2 — Phase 1 of `execution_plan.md`).

---

## [0.1.0] - 2026-09-11 — Step 1.1: Single PDF Ingestion Baseline

### Added
- `load_file()` in `ingestion.py` to handle path loading and PDF text extraction via `pypdf.PdfReader` page iteration.
- Pydantic data models `Document`, `TextChunk`, and `EmbeddedChunk` for strict type safety during schema transformation.
- Class-based pipeline (`RAGIndexingPipeline`) wiring `load_file()` → `chunk_document()` → `generate_embeddings()` → `upsert_to_vector_store()`.

### Changed
- Binary PDF documents can now be parsed; previously only plain-text sources were handled, leaving the vector store empty for `.pdf` policy files.

### Verified
- Ran `ingestion.py` targeting `data/raw/billing/AW-BIL-001_billing_dispute_policy.pdf`.
- `pipeline.run()` returns $>0$ `EmbeddedChunk` objects with extracted text and correct metadata (`category: "billing"`).
- Successfully extracted and indexed PDF text into chunk models with 1536-dimensional baseline vectors.

### Known Trade-offs
- Fixed-size character splitting is simple and fast, but may cut mid-sentence across page boundaries.

### Retrospective
- Engineering takeaway: Pydantic models ensure strict schema adherence during data transformation, preventing corrupted metadata down the line.

---

## [0.0.0] - 2026-09-11 — Step 0.1: Project Bootstrap

### Added
- Project skeleton via `uv init`; Python virtual environment created (`.venv`).

### Pending
- `pipeline/config.py` — Pydantic `PipelineConfig` as the single source of configuration.
- `core/db.py` — SQLAlchemy engine with connection pooling.
- `docker-compose.yml` — Postgres + pgvector service.
- `migrations/versions/0001_init.py` — migration enabling the vector extension.

### Problem
- No executable skeleton — impossible to test a stage without shared config or a shared DB connection.

### Approach
- `PipelineConfig` (Pydantic) as the single source of config; SQLAlchemy engine with connection pooling; migration 0 enables the vector extension.

### Target
- `docker-compose up` starts Postgres+pgvector, `pipeline db upgrade` runs without errors.

### Next
- Filesystem change detection (Step 1.1 — Phase 1 of `execution_plan.md`).