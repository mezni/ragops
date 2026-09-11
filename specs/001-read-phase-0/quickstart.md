# Quickstart: Project scaffolding (Phase 0)

Validation guide proving the scaffolding works end-to-end. It is a **run guide**,
not an implementation reference — details live in `data-model.md`, `contracts/`,
and `docs/ARCHITECTURE.md`.

## Prerequisites

- `docker` + `docker compose` plugin
- `uv` (>= 0.4) — package manager and Python provider
- Outbound access to pull `pgvector/pgvector:pg16`

## Setup

```bash
# 1. Install project deps into a uv-managed venv
uv sync

# 2. Prepare environment (never commit real secrets)
cp .env.example .env          # set DATABASE_URL, or rely on defaults below

# 3. Boot Postgres with pgvector (named volume persists data)
cd docker && docker compose up -d postgres
```

Default local database URL (match `.env.example`):

```
DATABASE_URL=postgresql+psycopg://ragops:ragops@localhost:5432/ragops
```

## Validate — Phase 0 exit criteria

| # | Scenario | Command | Expected outcome |
|---|---|---|---|
| 1 | Application starts cleanly | `python -m pipeline --help` | Help renders; exit `0` |
| 2 | Postgres reachable with pgvector image | `docker compose ps postgres` | `postgres` service `healthy` |
| 3 | Config loads and validates | `python -m pipeline healthcheck` | Prints `{"status":"ok",...}`; exit `0` |
| 4 | Migration 0001 applies `vector` extension | `python -m pipeline db upgrade` | Exit `0`, no errors |
| 5 | Extension actually created (idempotent) | re-run `python -m pipeline db upgrade` | Succeeds again — no "already exists" failure |
| 6 | `SELECT 1` round-trip succeeds | unit/integration test (below) | pytest passes |

## Tests

```bash
# Full suite: unit + integration (integration boots docker postgres)
uv run pytest

# Migrations + tests are also the CI gate (Phase 7), run on every push.
```

Requires the `postgres` service to be running (Setup step 3).

## Reference links

- Configuration contract: [`contracts/config-schema.md`](contracts/config-schema.md)
- CLI contract: [`contracts/cli.md`](contracts/cli.md)
- Data model & connection lifecycle: [`data-model.md`](data-model.md)
- Architecture: [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) (§7 Docker, §8 Database management)