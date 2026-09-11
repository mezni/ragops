# Contract: CLI surface

Version: `cli.v1` — Phase 0 scaffolding.

Exposed via `python -m pipeline` (Typer). Global `--config <path>` option
defaults to `config.yaml` at repo root.

## Commands

### `pipeline db upgrade`

Apply Alembic migrations to the configured database.

```
python -m pipeline db upgrade
```

**Behavior**:
- Load `PipelineConfig`; resolve `db.database_url`.
- Invoke Alembic `upgrade head` programmatically via `alembic.command`.
- Exit code `0` on success; non-zero on connection or migration failure.

**Exit codes**: `0` success, `1` config error, `2` connection/migration error.

### `pipeline healthcheck`

Verify Postgres reachability.

```
python -m pipeline healthcheck
```

**Behavior**: executes `SELECT 1` through the session factory. Prints JSON
`{"status":"ok","database_url_host":same}` on success.

**Exit codes**: `0` ok, `3` unhealthy.

### `pipeline --help` / `pipeline db --help`

Typer-generated help. Must document every command and the `--config` option.

## Rules

1. Migrations are **only** run via this command — never implicitly at app startup.
2. No command in this contract performs any business logic (parse/clean/chunk/
   embed); those arrive in later phases under their own commands.
3. CLI output to `stdout` for results, `stderr` for errors (Constitution pattern
   for CLI tooling).