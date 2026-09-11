---

description: "Task list template for feature implementation"
---

# Tasks: Project scaffolding

**Input**: Design documents from `/specs/001-read-phase-0/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks ARE included because the project constitution (`docs/CONSTITUTION.md` Article VI — "Nothing goes to production without test") mandates them, and plan.md gate G-4 requires a CI gate (migrations → tests → Docker build).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `pipeline/`, `migrations/`, `tests/`, `docker/` at repository root (per plan.md structure decision)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create repository structure per plan.md: `pipeline/`, `pipeline/core/`, `migrations/`, `tests/`, `tests/unit/`, `tests/integration/`, `docker/`
- [X] T002 Initialize uv project: create `pyproject.toml` with `requires-python >=3.12` and dependencies (sqlalchemy>=2.0, pydantic>=2, pydantic-settings, alembic, psycopg[binary]>=3, pgvector, typer>=0.12, pyyaml) per research.md R-1/R-2/R-5/R-6
- [X] T003 [P] Configure `pytest` + `pytest-xdist` in `pyproject.toml` per research.md R-8 (`[tool.pytest.ini_options]`, testpaths)
- [X] T004 [P] Create `config.yaml` with `db` and `logging` sections matching `contracts/config-schema.md`
- [X] T005 [P] Create `.env.example` with `DATABASE_URL` template and `LOG_LEVEL` (ensure `.env` stays gitignored)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement `PipelineConfig` (Pydantic v2 + pydantic-settings) in `pipeline/config.py` — loads `config.yaml` + env overrides `DATABASE_URL`/`LOG_LEVEL`, validation rules from `contracts/config-schema.md`
- [X] T007 [P] Implement structured JSON logging helper in `pipeline/core/logging.py` (single-line JSON, per research.md R-7 and `docs/ARCHITECTURE.md` §6)
- [X] T008 Implement SQLAlchemy engine/pool/session factory in `pipeline/core/db.py` (pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=1800, `postgresql+psycopg` dialect per research.md R-3/R-7)
- [X] T009 [P] Create `pipeline/__init__.py` and `pipeline/core/__init__.py` package markers

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Project Scaffolding Core (Priority: P1) 🎯 MVP

**Goal**: Stand up the executable skeleton — Docker topology, Alembic migrations, and the CLI (`db upgrade`, `healthcheck`) delivering the Phase 0 exit criteria from `docs/PLAN.md`.

**Independent Test**: `docker compose up -d postgres` starts Postgres with pgvector active; `python -m pipeline db upgrade` applies migrations without error; `python -m pipeline healthcheck` prints `{"status":"ok",...}`.

### Implementation for User Story 1

- [X] T010 [P] [US1] Create `docker/docker-compose.yml` with `postgres` service (image `pgvector/pgvector:pg16`, named volume `pgdata`) and `app` service (build `./docker`, depends_on postgres, env_file `.env`) per `docs/ARCHITECTURE.md` §7
- [X] T011 [P] [US1] Create `docker/Dockerfile` from `python:3.12-slim` that installs deps via `uv` and runs `python -m pipeline` (research.md R-9)
- [X] T012 [US1] Initialize Alembic: `migrations/env.py` + `migrations/script.py.mako` wired to `DATABASE_URL` from `PipelineConfig` (research.md R-10)
- [X] T013 [US1] Create migration `migrations/versions/0001_create_vector_extension.py`: `CREATE EXTENSION IF NOT EXISTS vector;` (idempotent, first migration — research.md R-4)
- [X] T014 [US1] Implement Typer CLI in `pipeline/cli.py`: `pipeline db upgrade` (Alembic upgrade head via `alembic.command`) and `pipeline healthcheck` (`SELECT 1`), per `contracts/cli.md`
- [X] T015 [US1] Add `pipeline/__main__.py` + `[project.scripts] pipeline = "pipeline.cli:app"` entry point so `python -m pipeline` works

**Checkpoint**: User Story 1 delivers the Phase 0 sprint goal — skeleton is executable end-to-end.

---

## Phase 4: User Story 2 - Verify Scaffolding Content (Priority: P2)

**Goal**: Prove the scaffold is correct and well-structured via tests: config validation, engine/session lifecycle, and an end-to-end migration + `SELECT 1` (Constitution Article VI).

**Independent Test**: `uv run pytest` passes with the docker `postgres` service running — unit tests (`config`, `db`) and the integration test (`db upgrade` → `SELECT 1`).

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T016 [P] [US2] Create test fixture in `tests/conftest.py` booting the docker `postgres` service and exposing a `DATABASE_URL`-bound session factory
- [X] T017 [P] [US2] Unit test `PipelineConfig` validation (required URL, pool bounds, log-level enum, env override precedence) in `tests/unit/test_config.py`
- [X] T018 [US2] Unit test engine/session lifecycle (pool created, pre-ping, `SELECT 1` round-trip) in `tests/unit/test_db.py`

### Implementation for User Story 2

- [X] T019 [US2] Integration test `tests/integration/test_db_upgrade.py`: run `pipeline db upgrade` against the fixture DB, assert the `vector` extension is listed in `pg_extension`, then execute `SELECT 1`

**Checkpoint**: User Stories 1 AND 2 both work — the scaffold is verified, not just created.

---

## Phase 5: User Story 3 - Plan Navigation & Docs (Priority: P3)

**Goal**: Make the scaffold navigable — documentation linking plan, contracts, data model, and quickstart so contributors can locate any part of the Phase 0 deliverable.

**Independent Test**: README + quickstart provide runnable, correct navigation — a contributor can start from the root README, follow to `quickstart.md`, and complete every validation scenario.

### Implementation for User Story 3

- [X] T020 [P] [US3] Verify and extend existing `specs/001-read-phase-0/quickstart.md` validation guide — confirm prereqs, setup, 6 scenarios, and test commands match `contracts/cli.md`; add missing entries only if a scenario is absent
- [X] T021 [US3] Update root `README.md` with scaffold structure overview and pointers to `docs/ARCHITECTURE.md`, `docs/PLAN.md`, and the quickstart
- [X] T022 [US3] Verify `contracts/index.md` links to config-schema and cli contracts in `specs/001-read-phase-0/contracts/` (links established during plan phase)

**Checkpoint**: All user stories independently functional and the scaffold is fully documented.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T023 Add CI workflow (e.g. `.github/workflows/ci.yml`) running: `uv sync` → migrations → tests → Docker image build, on every push (plan.md gate G-4, `docs/PLAN.md` Phase 7 precursor)
- [X] T024 [P] Add `README.md` → config contract example copy-correctness check (`config.yaml` matches `contracts/config-schema.md`)
- [X] T025 Run `specs/001-read-phase-0/quickstart.md` validation end-to-end and resolve any failures
- [X] T026 Verify Constitution compliance: no hardcoded provider values (Article II), explicit migrations only (Article VI), no business logic added (Article VII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (T008 `db.py` needed by CLI healthcheck)
- **User Story 2 (Phase 4)**: Depends on US1 (tests exercise `db upgrade` / engine); can start its test tasks once T008 exists
- **User Story 3 (Phase 5)**: Depends on US1 + US2 (docs reference final CLI and validated quickstart)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: After Foundational — no cross-story dependencies
- **User Story 2 (P2)**: After Foundational + US1 CLI/migrations exist — independently testable
- **User Story 3 (P3)**: After US1 + US2 — documentation-only, no code coupling

### Within Each User Story

- Foundational primitives (config → db) before CLI/story work
- Tests (US2) written before implementation, verified failing first
- Core implementation before documentation

### Parallel Opportunities

- T003/T004/T005 (Setup) run in parallel — independent files
- T007/T009 (Foundational) run in parallel
- T010/T011 run in parallel; then T012→T013→T014→T015 sequentially (Alembic → migration → CLI → entry point)
- T016/T017 run in parallel; then T018→T019 sequentially
- T020/T022 run in parallel; T021 last (depends on structure being stable)

---

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Create test fixture in tests/conftest.py booting docker postgres"
Task: "Unit test PipelineConfig validation in tests/unit/test_config.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `docker compose up -d postgres` && `python -m pipeline db upgrade` && `python -m pipeline healthcheck`
5. This satisfies the `docs/PLAN.md` Phase 0 exit criteria — the MVP is a runnable scaffold.

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. User Story 1 → validate exit criteria → demo (MVP!)
3. User Story 2 → verified scaffold (tests green)
4. User Story 3 → navigable, documented scaffold
5. Polish → CI gate locks the scaffold against regressions

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Docker + migrations + CLI)
   - Developer B: User Story 2 test scaffolding (fixture, unit tests)
   - Developer C: User Story 3 docs (quickstart, README cross-links)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (US2)
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence