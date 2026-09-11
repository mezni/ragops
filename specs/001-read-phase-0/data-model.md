# Data Model: Project scaffolding (Phase 0)

Phase 0 introduces **no persistent business tables**. It establishes the data
layer foundation only: an empty (extension-bearing) database against which
later phases create `documents`, `pipeline_runs`, `index_versions`,
`chunks_<dimension>`, and `evaluations` (see `docs/ARCHITECTURE.md` §4).

The only schema artifact produced in this phase is a QQL-managed state machine
is not present; instead, what Phase 0 owns is:

1. The `vector` extension (migration `0001`).
2. The validated configuration model (`PipelineConfig`).
3. The connection lifecycle (engine + pool + session factory).

## Entities

### `PipelineConfig` (configuration model, not a DB table)

| Field | Type | Default | Validation / Notes |
|---|---|---|---|
| `db.database_url` | str (secret) | required | `postgresql+psycopg://...`; env-overridable via `DATABASE_URL` |
| `db.pool_size` | int | `5` | ≥ 1 |
| `db.max_overflow` | int | `10` | ≥ 0 |
| `db.pool_pre_ping` | bool | `True` | fixed contract |
| `db.pool_recycle` | int | `1800` | seconds, ≥ 60 |
| `db.echo` | bool | `False` | SQL echo (dev) |
| `logging.level` | enum | `"INFO"` | `DEBUG/INFO/WARNING/ERROR` |

**Relationships**: none (standalone config aggregate loaded once at CLI start).

**State transitions**: immutable after load; a run uses one config snapshot.
Full `config_snapshot` persistence happens at the `pipeline_runs` table in
Phase 6.

### `vector` Postgres extension

| Field | Value |
|---|---|
| Type | Postgres extension (`CREATE EXTENSION IF NOT EXISTS vector`) |
| Owner migration | `migrations/versions/0001_create_vector_extension.py` |
| Version | provided by `pgvector/pgvector:pg16` image |

**Validation**: migration must be idempotent; the extension must exist before
any `VECTOR` column is ever created (later phases).

## Validation rules

- `DATABASE_URL` must parse to the `postgresql+psycopg` dialect; invalid URL or
  unreachable host fails fast at CLI start with a clear error.
- Configuration is fully validated at construction time by Pydantic
  (Constitution Article II — no hardcoded provider values in code).

## State transitions

None for entities this phase. The relevant lifecycle is the **connection
lifecycle**:

```text
config load → create_engine(pool) → session factory → [open/commit/close per document in later phases]
```

All access flows through `pipeline.core.db`; no ad-hoc connections.

## Notes for later phases

- `documents`, `pipeline_runs`, `index_versions`, `evaluations`: added in
  Phases 1, 6, 5, 8 respectively (see `docs/PLAN.md`).
- `chunks_<dimension>` tables are created at runtime by `SchemaManager`
  (architecture §8), not by static migrations.
- Migrations must remain append-only and versioned (Constitution Article VI).