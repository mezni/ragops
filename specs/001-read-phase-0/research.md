# Research: Project scaffolding (Phase 0)

Resolves every `NEEDS CLARIFICATION` surfaced in `plan.md` Technical Context and
records the technology choices with rationale. Source of record for the design
decisions in `data-model.md`, `contracts/`, and `quickstart.md`.

## R-1: Python version

- **Decision**: Python 3.12, pinned via `uv` (`.python-version` + `requires-python >=3.12`).
- **Rationale**: `pgvector` bindings, SQLAlchemy 2.x async, Pydantic v2, and `typer`
  all support 3.12 maturely; 3.12 is the current stable line with wide Docker
  image availability (`python:3.12-slim`). One universal version avoids the
  per-container drift of "some flavor of recent Python".
- **Alternatives considered**:
  - Python 3.13 — newer but with spotty C-extension wheel coverage for
    `psycopg`/`pgvector` in some base images at planning time.
  - Python 3.11 — safe but older; no benefit for a greenfield project.

## R-2: Package manager

- **Decision**: `uv` for dependency resolution, venv creation, lockfile, and CI installs.
- **Rationale**: The user selected `uv` and it is already documented in
  `docs/PRD.md` (replaces pip/poetry). `uv` produces a single reproducible
  `uv.lock`, is dramatically faster than pip/poetry, and is the project's
  declared convention.
- **Alternatives considered**: pip + requirements.txt (no lockfile resolution),
  Poetry (heavier, slower), pip-tools (extra tooling, comments-in-lock friction).

## R-3: Database driver + SQLAlchemy version

- **Decision**: SQLAlchemy 2.x with `psycopg[binary]>=3` and the
  `postgresql+psycopg` dialect.
- **Rationale**: SQLAlchemy 2.0 is the current major (typed ORM/Core, modern
  session patterns). `psycopg3` is the maintained driver with first-class
  support in SQLAlchemy 2 and works cleanly with `pgvector`'s Python bindings.
- **Alternatives considered**: asyncpg (async-only; pipeline is batch/sync
  oriented, async adds complexity with no current requirement), psycopg2
  (legacy, deprecated in favor of psycopg3).

## R-4: pgvector extension management

- **Decision**: The `pgvector` Postgres extension is provided by the image
  (`pgvector/pgvector:pg16`) and activated by Alembic migration `0001`
  (`CREATE EXTENSION IF NOT EXISTS vector;`), executed at `pipeline db upgrade`.
- **Rationale**: Declarative, idempotent, versioned — matches `docs/PLAN.md`
  Phase 0 ("migration 0") and keeps extension creation in the same upgrade path
  as all other schema changes. Explicit `db upgrade` (never at app start)
  prevents concurrent-deployment migration races (architecture §8).
- **Alternatives considered**: init script in the container (runs outside the
  Alembic version history — untraceable), auto-run `create_ext` on app boot
  (violates the explicit-migrations rule).

## R-5: Configuration loading (PipelineConfig)

- **Decision**: Pydantic v2 + `pydantic-settings`. `PipelineConfig` reads
  `config.yaml` (core values) with environment overrides from `.env` /
  `os.environ` for secrets and URLs; loading is validated at construction.
- **Rationale**: Constitution Article II — provider/configurable values are
  resolved from validated config, never hardcoded. Pydantic v2 is already the
  project's validating-config standard (`brief.md`/`architecture.md` reference
  `PipelineConfig (Pydantic)`). Settings source precedence:
  env > `.env` > `config.yaml` > defaults.
- **Alternatives considered**: plain dataclasses (no validation/schema),
  `dynaconf` (extra dependency, heavier than needed).

## R-6: CLI framework

- **Decision**: `typer>=0.12` exposing commands under `python -m pipeline`:
  `pipeline db upgrade`, `pipeline healthcheck` (initial), plus a `--config`
  global option.
- **Rationale**: Native type hints + validation match the Pydantic stack;
  `docs/ARCHITECTURE.md` calls for `pipeline db upgrade` and a health check
  (`SELECT 1`); Typer gives shell completion and structured errors for free.
- **Alternatives considered**: Click (fine but manual typing), argparse
  (verbose, no rich help), manually-parsed `sys.argv` (rejected outright).

## R-7: Connection pool sizing

- **Decision**: Pool defaults in `PipelineConfig`: `pool_size=5`,
  `max_overflow=10`, `pool_pre_ping=True`, `pool_recycle=1800`.
- **Rationale**: A single-file-at-a-time per-document transaction model needs
  modest concurrency; these defaults avoid exhausting a small Postgres
  container while leaving headroom. `pool_pre_ping` survives container restarts.
- **Alternatives considered**: No pool (open/close per document — high
  overhead), large pool (unnecessary for one indexer process).

## R-8: Testing strategy for Phase 0

- **Decision**: `pytest` unit tests (config, engine/session factory) plus an
  integration test that boots the docker-compose `postgres` service and runs
  `pipeline db upgrade` against it, ending with `SELECT 1`.
- **Rationale**: Constitution Article VI — everything entering production needs
  a test. The DB-backed integration test is the closest real proof of the Phase 0
  exit criteria without hand-waving.
- **Alternatives considered**: SQLite-based tests (pgvector extension is
  Postgres-only — would test the wrong thing), mocking the engine entirely
  (tests nothing real about migrations).

## R-9: Docker layout

- **Decision**: Two services in `docker/docker-compose.yml`: `postgres`
  (`pgvector/pgvector:pg16`) with a named volume, and `app` built from
  `docker/Dockerfile` (python:3.12-slim) that depends on `postgres`, mounts
  nothing yet (source volume added in Phase 1+), and reads `.env`.
- **Rationale**: Matches `docs/ARCHITECTURE.md` §7 topology and `PLAN.md`
  Phase 0 exit criteria (`docker-compose up` starts Postgres with pgvector).
  Health-check via `app`'s `pipeline healthcheck` (`SELECT 1`).
- **Alternatives considered**: Single container running both (coupling of data
  and app; hard to scale/index maintenance), compose at repo root instead of
  `docker/` (documented layout uses `docker/`).

## R-10: Initial Alembic setup

- **Decision**: Bare Alembic (not `alembic init` defaults matching app):
  `migrations/env.py` targeting the `DATABASE_URL` from config, `migration
  0001` adding the `vector` extension. Metadata target = empty (no tables yet;
  tables arrive with `documents` in Phase 1).
- **Rationale**: Keep the migration history clean; an empty baseline is the
  right state before the first real table. `pipeline db upgrade` shells out to
  Alembic programmatically (`alembic.command.upgrade`), not subprocess.
- **Alternatives considered**: `alembic init` default tree at repo root (mixes
  tooling and app code against the documented layout), SQL executed by hand
  (`SELECT 1` healthcheck would pass without the extension present).

## Open items resolved during research

None — all `plan.md` unknowns resolved above. The full dependency set and exact
pins are captured in `contracts/config-schema.md` and `quickstart.md`.