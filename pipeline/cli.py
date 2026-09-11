"""CLI surface: ``pipeline db upgrade`` and ``pipeline healthcheck``.

Contract: `contracts/cli.md` (cli.v1).
Output: results to stdout, errors to stderr.
"""

from __future__ import annotations

from pathlib import Path

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from pipeline.config import DEFAULT_CONFIG_PATH, PipelineConfig, load_config
from pipeline.core.db import check_connection, create_db_engine

app = typer.Typer(
    help="RAG indexing pipeline — Phase 0 scaffolding.",
    no_args_is_help=True,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _load_config(config_path: Path) -> PipelineConfig:
    try:
        return load_config(config_path)
    except Exception as exc:  # noqa: BLE001 — exit code 1 is reserved for config errors
        typer.secho(f"Configuration error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def _alembic_configuration(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@app.callback()
def main(config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to config.yaml.")) -> None:
    """Load and validate configuration up front."""
    _load_config(config)


@app.command("healthcheck")
def healthcheck(config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to config.yaml.")) -> None:
    """Verify Postgres reachability via ``SELECT 1``."""
    pipeline_config = _load_config(config)
    engine = create_db_engine(pipeline_config)
    try:
        check_connection(engine)
    except Exception as exc:  # noqa: BLE001 — any failure means unhealthy
        typer.secho(f"Unhealthy: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(3) from exc

    host = pipeline_config.db.database_url.split("://")[-1].split("/")[0]
    typer.echo(f'{{"status":"ok","database_url_host":"{host}"}}')


db_app = typer.Typer(
    help="Database management commands (migrations via Alembic).",
    no_args_is_help=True,
)
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade(config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Path to config.yaml.")) -> None:
    """Apply Alembic migrations up to head.

    Exit codes: 0 success, 1 config error, 2 connection/migration error.
    """
    pipeline_config = _load_config(config)
    cfg = _alembic_configuration(pipeline_config.db.database_url)
    try:
        alembic_command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001 — migration/connection failure
        typer.secho(f"Migration error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(2) from exc
    typer.secho("Database migrated to head.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()