# Contract: index

Version: `contracts.v1` — Phase 0 scaffolding.

This directory documents the stable external contracts established by the
Project scaffolding feature.

| Contract | Purpose | Owner |
|---|---|---|
| [config-schema.md](config-schema.md) | Validated pipeline configuration model (`PipelineConfig`) | `pipeline/config.py` |
| [cli.md](cli.md) | CLI surface: `pipeline db upgrade`, `pipeline healthcheck` | `pipeline/cli.py` |

Interfaces for parsers/cleaners/chunkers/enrichers/embedders (Protocols) will
be added here by their respective phases (see `docs/ARCHITECTURE.md` §5) — they
are intentionally out of scope for scaffolding.