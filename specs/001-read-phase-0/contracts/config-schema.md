# Contract: PipelineConfig schema

Version: `config-schema.v1` — Phase 0 scaffolding.

Canonical configuration model for the pipeline. Validated by Pydantic v2.
Source precedence: environment > `.env` > `config.yaml` > defaults.

## `config.yaml` shape

```yaml
db:
  database_url: ${DATABASE_URL}      # postgresql+psycopg://user:pass@host:5432/db
  pool_size: 5
  max_overflow: 10
  pool_pre_ping: true
  pool_recycle: 1800
  echo: false

logging:
  level: INFO                        # DEBUG | INFO | WARNING | ERROR
```

## Environment overrides

| Env var | Overrides |
|---|---|
| `DATABASE_URL` | `db.database_url` |
| `LOG_LEVEL` | `logging.level` |

## Validation rules

1. `db.database_url` required, must be a valid `postgresql+psycopg://` URL.
2. `db.pool_size` ≥ 1, `db.max_overflow` ≥ 0, `db.pool_recycle` ≥ 60.
3. `logging.level` ∈ `{DEBUG, INFO, WARNING, ERROR}`.
4. Unknown top-level keys → validation error (fail fast).
5. Configuration is loaded once at CLI start and immutable afterwards.

## Backwards compatibility

`config-schema.v1` is the initial contract. Schema changes must go through the
amendment process in `docs/CONSTITUTION.md` and a MINOR/PATCH bump of this
contract before being consumed by later phases.