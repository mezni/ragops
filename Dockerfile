FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install project dependencies first (leveraging Docker layer cache) --
# the project itself is installed in a later layer, so changes to source
# don't invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application sources and Alembic environment
COPY core ./core
COPY alembic ./alembic
COPY alembic.ini ./

# Apply the (already cached) sync that installs the project package.
RUN uv sync --frozen --no-dev

# Pipeline entrypoint. Wire `main.py` into the pipeline via the
# following CMD once the ingestion/run entrypoint lands:
CMD ["uv", "run", "--no-sync", "python", "main.py"]