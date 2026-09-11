# Feature Specification: Project scaffolding

**Feature Branch**: `[001-read-phase-0]`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "Project scaffolding — read Phase 0 plan"

## Overview

Phase 0 of the RAG indexing pipeline: deliver an executable skeleton with
**no business logic** (Constitution Article VII). The "read Phase 0 plan"
story is the entry point — the scaffold goals, exit criteria, and
implementation order are defined in `docs/PLAN.md` Phase 0. This spec
operationalizes those goals into concrete artifacts: repository layout
(`docs/ARCHITECTURE.md` §3), a Docker topology (Postgres + pgvector + app), a
Pydantic-validated `PipelineConfig`, a SQLAlchemy engine/pool/session factory,
an Alembic initialization with a `CREATE EXTENSION IF NOT EXISTS vector`
migration, and a CLI (`pipeline db upgrade`, `pipeline healthcheck`).

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Scaffold Core (Priority: P1)

As a new contributor, I want a runnable project skeleton so that I can boot
Postgres with pgvector, apply migrations, and verify connectivity from day one.

**Why this priority**: P1 — the executable skeleton is the Phase 0 sprint goal
and the prerequisite for all later phases; nothing else in the scaffold can be
demonstrated without it.

**Independent Test**: `docker compose up -d postgres` starts Postgres with
pgvector; `python -m pipeline db upgrade` applies migration 0001 without
error; `python -m pipeline healthcheck` prints `{"status":"ok",...}` and
exits `0`.

**Acceptance Scenarios**:
1. **Given** the repository is checked out, **When** I run `docker compose up -d postgres` from `docker/`, **Then** the `postgres` service becomes `healthy` running the `pgvector/pgvector:pg16` image.
2. **Given** Postgres is up, **When** I run `python -m pipeline db upgrade`, **Then** migration 0001 applies the `vector` extension and the command exits `0`.
3. **Given** migration 0001 has run, **When** I run `python -m pipeline healthcheck`, **Then** a `SELECT 1` succeeds through the configured session factory and the command prints `{"status":"ok",...}`.

---

### User Story 2 - Verify Scaffolding Content (Priority: P2)

As a reviewer, I want the scaffold verified by tests so that I can trust the
skeleton is correctly configured before referencing it in later phases.

**Why this priority**: P2 — content verification (Constitution Article VI)
ensures the skeleton is not broken or misconfigured before teams build on it.

**Independent Test**: `uv run pytest` passes with the docker `postgres`
service running — unit tests (config validation, engine/session lifecycle) and
an integration test (`db upgrade` → vector extension present → `SELECT 1`).

**Acceptance Scenarios**:
1. **Given** the docker `postgres` service is running, **When** I run `uv run pytest`, **Then** the full suite (unit + integration) passes.
2. **Given** the config contract, **When** `PipelineConfig` is constructed from `config.yaml` and env overrides, **Then** validation rules from `contracts/config-schema.md` are enforced.
3. **Given** the integration test, **When** migrations are applied to the fixture DB, **Then** the `vector` extension is listed in `pg_extension` and `SELECT 1` succeeds.

---

### User Story 3 - Plan Navigation & Docs (Priority: P3)

As an explorer, I want the scaffold documented and navigable so that I can find
the plan, contracts, data model, and quickstart without hunting through the
repository.

**Why this priority**: P3 — good navigation improves contributor onboarding and
helps reference the plan across sessions.

**Independent Test**: README + quickstart provide runnable, correct navigation —
a contributor can start from the root README, follow to `quickstart.md`, and
complete every validation scenario.

**Acceptance Scenarios**:
1. **Given** the repository root, **When** I read the README, **Then** it points to `docs/ARCHITECTURE.md`, `docs/PLAN.md`, and the quickstart.
2. **Given** the quickstart, **When** I follow its validation scenarios, **Then** each scenario's command and expected outcome from the table match the actual CLI behavior.
3. **Given** the contracts directory, **When** I read `contracts/index.md`, **Then** it links to the config-schema and CLI contracts.

---

### Edge Cases

- **Database unreachable**: `pipeline db upgrade` / `pipeline healthcheck` against a down Postgres → non-zero exit (`2` connection error, `3` unhealthy) with a clear error to `stderr`, never a hang.
- **Re-running migrations**: `python -m pipeline db upgrade` twice → idempotent; `CREATE EXTENSION IF NOT EXISTS vector` succeeds without "already exists".
- **Missing `.env`**: config construction fails validation with a clear message identifying the missing variable — no silent fallback to a real secret.
- **Container restart / dropped connection**: `pool_pre_ping` recovers from a restarted Postgres without failing the run.
- **`.env` missing `DATABASE_URL`**: pipeline falls back to documented defaults (as validated by `PipelineConfig`); nothing is hardcoded in business logic (Article II).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a runnable Python project scaffold pinned to Python 3.12 via `uv` (`pyproject.toml`, `requires-python >=3.12`, `uv.lock`)
- **FR-002**: System MUST expose a validated `PipelineConfig` (Pydantic v2 + `pydantic-settings`) loading `config.yaml` with env overrides (`DATABASE_URL`, `LOG_LEVEL`)
- **FR-003**: System MUST boot PostgreSQL 16 with the pgvector extension via `docker/docker-compose.yml` (`postgres` + `app` services, named volume `pgdata`)
- **FR-004**: System MUST apply migrations explicitly via `pipeline db upgrade`; migration `0001` enables the `vector` extension idempotently; never at app startup
- **FR-005**: System MUST provide `pipeline healthcheck` executing `SELECT 1` through the session factory of `core/db.py`
- **FR-006**: System MUST confine DB access to the engine/pool/session factory in `pipeline/core/db.py` (never ad-hoc connections)

### Success Criteria *(mandatory)*

- **SC-001**: `docker compose up -d postgres` starts the `postgres` service with pgvector active (service `healthy`)
- **SC-002**: `python -m pipeline db upgrade` applies migration 0001 without error, and succeeds again on re-run (idempotent)
- **SC-003**: `python -m pipeline healthcheck` prints `{"status":"ok",...}` and exits `0`
- **SC-004**: `uv run pytest` passes the full suite (unit + integration) with the docker `postgres` service running

## Assumptions

- The authoritative constitution is `docs/CONSTITUTION.md` (Articles I–VII); the Spec Kit template at `.specify/memory/constitution.md` is a reference copy.
- Users have Docker (`docker compose` plugin) and `uv` (>= 0.4) installed.
- Postgres runs locally in Docker; no managed/external Postgres in scope for Phase 0.
- `.env` carries secrets and is gitignored; `config.yaml` carries non-secret defaults.
- Scope is scaffolding only — no parsing/chunking/embedding/storage logic (Article VII); `indexing/` is deferred to later phases.