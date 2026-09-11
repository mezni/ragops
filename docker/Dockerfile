# RAG indexing pipeline — app image (Phase 0 scaffolding)
#
# Phase 0: base image with uv. Source is injected via a bind-mount in Phase 1+
# (research.md R-9). The image is intentionally minimal — no business logic yet.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv as the package manager (research.md R-1/R-2)
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy

# Phase 0 scaffold: image ready for source injection in Phase 1+.
CMD ["uv", "--version"]