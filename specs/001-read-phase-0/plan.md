# Implementation Plan: Project scaffolding

**Branch**: `001-read-phase-0` | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-read-phase-0/spec.md`

## Summary

Phase 0 — Project scaffolding for the RAG indexing pipeline (see `docs/PLAN.md`).
Deliver an executable skeleton with **no business logic**: the repository layout
documented in `docs/ARCHITECTURE.md` §3, a working `docker-compose.yml`
(Postgres + pgvector + app), Pydantic-validated `PipelineConfig`, a SQLAlchemy
engine/pool/session factory (`core/db.py`), an Alembic initialization with a
`CREATE EXTENSION IF NOT EXISTS vector` migration, a health check, and an
explicit `pipeline db upgrade` CLI command.

The user story of "reading the Phase 0 plan" is the entry point: confirming the
scaffold goals and exit criteria (`docs/PLAN.md` Phase 0) is the specification
of record. This plan operationalizes those goals into concrete artifacts.

## Technical Context

**Language/Version**: Python 3.12 (managed by `uv`; `python-version` pinned in root)

**Primary Dependencies**:
- `sqlalchemy>=2.0` — engine, pool, session factory
- `pydantic>=2` / `pydantic-settings` — `PipelineConfig`, YAML + env loading
- `alembic` — versioned migrations
- `psycopg[binary]>=3` — Postgres driver (SQLAlchemy 2 dialect `postgresql+psycopg`)
- `pgvector` — Python bindings for the `vector` type
- `typer>=0.12` — CLI (`python -m pipeline`)
- `pyyaml` — `config.yaml` parsing

**Storage**: PostgreSQL 16 image `pgvector/pgvector:pg16` (Docker), extension activated by the initial Alembic migration.

**Testing**: `pytest` + `pytest-xdist`; DB-backed tests via real Postgres container (docker-compose `postgres` service). CI phase runs migrations + tests + Docker image build.

**Target Platform**: Linux (Docker) — `app` service built from `docker/Dockerfile`.

**Project Type**: CLI tool + background pipeline (cron-orchestrated). Single Python project at repo root (`pip`-style flat layout: `pipeline/` package, `tests/`, `migrations/`, `docker/`).

**Performance Goals**: N/A for scaffolding. Franchise constraints for later phases: batched embedding calls, per-document transactions. Nothing to tune at Phase 0 beyond a healthy connection pool.

**Constraints**:
- DB access only through `core/db.py` engine/pool/session factory (never ad-hoc connections).
- Migrations executed explicitly via `pipeline db upgrade` — never at app startup (avoids concurrent-migration races).
- Secrets via `.env` only; `.env` is gitignored.
- `CREATE EXTENSION IF NOT EXISTS vector;` must be migration `0001`, before any table.
- Scope is scaffolding only — no parsing/chunking/embedding/storage logic (Constitution Article VII).

**Scale/Scope**: Single indexer process, one filesystem source root, Postgres with pgvector. No multi-node, no horizontal scaling in scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Source of principles: `docs/CONSTITUTION.md` (Articles I–VII). The Spec Kit constitution template at `.specify/memory/constitution.md` is unfilled; the project constitution in `docs/` is authoritative.

| Gate | Constitution Article | Status |
|---|---|---|
| G-1: Provider/configurable values resolved via validated Pydantic config, never hardcoded | II | PASS — `PipelineConfig` from `config.yaml` + `.env`, validated/env-overridable (`contracts/config-schema.md`) |
| G-2: No physical deletion; everything traceable | I | PASS (not applicable) — scaffolding introduces no data lifecycle |
| G-3: Local failure isolated, no concurrent runs | III | PASS (not applicable) — `pg_advisory_lock` is Phase 6; scaffolding only establishes db layer |
| G-4: Nothing enters production without tests + CI gate | VI | PASS — pytest scaffold (unit + integration) and CI gate defined in `quickstart.md` |
| G-5: Scope discipline — only scaffolding, no speculative features | VII | PASS — design excludes business logic and backlog items; `indexing/` deferred |
| G-6: Cost/latency as design constraints | V | N/A — no external paid calls in scaffolding |

*Post-design re-check (Phase 1 complete): all applicable gates PASS. G-1, G-4,
G-5 verified against the generated artifacts (config contract, CLI contract,
quickstart validation scenarios).*

## Project Structure

### Documentation (this feature)

```text
specs/001-read-phase-0/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
rag-indexer/                        # single project (flat layout)
├── pipeline/
│   ├── __init__.py
│   ├── config.py                   # PipelineConfig (Pydantic), YAML/env loading
│   ├── cli.py                      # typer app: `pipeline db upgrade`, healthcheck
│   └── core/
│       ├── __init__.py
│       ├── db.py                   # SQLAlchemy engine, pool, session factory
│       └── logging.py              # structured JSON logging (minimal, Phase 6 baseline)
├── migrations/                     # Alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_create_vector_extension.py
├── tests/
│   ├── conftest.py                 # fixture: DATABASE_URL via docker postgres
│   ├── unit/
│   │   ├── test_config.py
│   │   └── test_db.py
│   └── integration/
│       └── test_db_upgrade.py      # end-to-end: migrate + SELECT 1
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── config.yaml
├── .env.example
├── pyproject.toml                  # uv-managed, includes pytest config
├── uv.lock
└── README.md
```

**Structure Decision**: Single flat Python project (Option 1). The pipeline will be one deployable (the `app` image) plus Postgres; the `core/` / `indexing/` split from `docs/ARCHITECTURE.md` §3 is preserved, but `indexing/` is intentionally absent until Phases 1–5 add it — scaffolding stays to the skeleton.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations — the Complexity Tracking table is not required.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | — | — |