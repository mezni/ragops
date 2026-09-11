# RAGOps — RAG Indexing Pipeline

Phase 0 project scaffolding: an executable skeleton with **no business logic**
(`docs/CONSTITUTION.md` Article VII). Postgres 16 + pgvector, Pydantic-validated
config, SQLAlchemy engine/session factory, Alembic migrations, and a Typer CLI.

## Structure

```
pipeline/          # app package (config, CLI, core/db, core/logging)
migrations/        # Alembic (versions/0001 = vector extension)
tests/             # unit + integration (boots docker postgres)
docker/            # Dockerfile + docker-compose.yml (postgres + app)
config.yaml        # non-secret defaults
.env.example       # env template (copy to .env; never commit)
```

## Quick start

```bash
uv sync                          # install deps (Python 3.12 via uv)
cp .env.example .env             # set DATABASE_URL / LOG_LEVEL
cd docker && docker compose up -d postgres
uv run python -m pipeline db upgrade      # run Alembic migrations
uv run python -m pipeline healthcheck     # SELECT 1 -> {"status":"ok",...}
uv run pytest                    # unit + integration tests
```

## Documentation

- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (§3 layout, §7 Docker, §8 DB management)
- Plan: [`docs/PLAN.md`](docs/PLAN.md) (Phase 0 exit criteria, later phases)
- Constitution: [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md)
- PRD: [`docs/PRD.md`](docs/PRD.md)
- Feature scaffolding quickstart: [`specs/001-read-phase-0/quickstart.md`](specs/001-read-phase-0/quickstart.md)
- Contracts: [`specs/001-read-phase-0/contracts/`](specs/001-read-phase-0/contracts/)