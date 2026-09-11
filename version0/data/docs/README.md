# ragops

A RAG (Retrieval-Augmented Generation) pipeline system for document ingestion, chunking, embedding, and retrieval.

## 📦 Installation

```bash
uv venv
uv pip install -r requirements.txt
```

## 🚀 Quick Start

### Run the indexing pipeline

```bash
python main.py index --source-dir ./data/docs
```

### Run database migrations

```bash
python main.py migrate --message "initial_schema"
```

### Launch the Streamlit UI

```bash
python main.py ui
```

### Run evaluation benchmarks

```bash
python main.py evaluate --dataset ./evaluation/datasets/ground_truth.json
```

### Execute a RAG query

```bash
python main.py query "What is the capital of France?"
```

## 📁 Project Structure

```
ragops/
├── main.py                          # CLI entry point with Typer
├── pyproject.toml                   # Project configuration
├── uv.lock                          # Lock file for reproducible deps
├── requirements.txt                 # Pinned dependencies
├── core/                            # Core infrastructure
│   ├── __init__.py
│   ├── config.py                    # Pydantic-settings configuration
│   ├── logging.py                   # structlog-based JSON/console logging
│   ├── pipeline.py                  # PipelineStage + GeneralizedPipeline engine
│   └── database.py                  # SQLAlchemy ORM models + DatabaseManager
├── indexing/                        # Indexing pipeline stages
│   ├── __init__.py
│   ├── stages/                      # Concrete pipeline stages
│   │   ├── __init__.py
│   │   ├── ingestion.py             # Payload version sync + format parsing
│   │   ├── chunking.py              # Sliding-window text chunking
│   │   ├── embedding.py             # OpenAI / deterministic embedding vectors
│   │   └── models.py                # TextChunk / EmbeddedChunk data structures
│   └── builder.py                   # Pipeline orchestrator (build_indexing_pipeline, run_indexing_pipeline)
├── parsers/                         # Format-specific parsers (PDF, Markdown, Text)
├── loaders/                         # Source data loaders (filesystem, database, API)
├── alembic/                         # Database migration framework
├── tests/                           # Full test suite (56 unit + integration tests)
└── README.md                        # You are here
```

## 🛠️ Pipeline Architecture

### PipelineStage Base Class

All stages inherit from `PipelineStage[I, O]` with `stage_name` and `execute(input_data, context)`:

```python
from core.pipeline import PipelineStage, GeneralizedPipeline

class MyStage(PipelineStage[InputType, OutputType]):
    def execute(self, input_data, context):
        # transform input -> output using shared context
        pass
```

### Three-Stage Indexing Pipeline

| Stage | Input | Output | Purpose |
|------|-------|--------|---------|
| `IngestionStage` | `List[RawPayload]` | `List[Document]` | Version sync via `DatabaseManager`, format routing to parser, `DocumentModel` persistence |
| `ChunkingStage` | `List[Document]` | `List[TextChunk]` | Sliding-window character-window chunking (`CHUNK_SIZE`, `CHUNK_OVERLAP`) |
| `EmbeddingStage` | `List[TextChunk]` | `List[EmbeddedChunk]` | OpenAI embeddings when `OPENAI_API_KEY` set; else deterministic 1536-dim MD5 fallback |

### GeneralizedPipeline Engine

```python
from core.pipeline import GeneralizedPipeline
from indexing.builder import build_indexing_pipeline

pipeline = build_indexing_pipeline()
# GeneralizedPipeline[List[RawPayload], List[EmbeddedChunk]]
result = pipeline.run(initial_input=raw_payloads, context={"db_manager": db})
```

## 📚 CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py index --source-dir ./data` | Ingest, chunk, embed documents from a directory |
| `python main.py migrate --message "initial_schema"` | Create and apply Alembic migrations |
| `python main.py query "your question" --top-k 5` | RAG query (retrieval pipeline pending) |
| `python main.py evaluate --dataset ./data.json` | Run quality benchmarks (Hit Rate, MRR, Faithfulness) |
| `python main.py ui` | Launch Streamlit web interface |

### CLI Options

```bash
python main.py index --source-dir ./data/docs --no-recursive
python main.py migrate -m "add vector column"
python main.py query "What is RAG?" --top-k 10
```

## ⚙️ Configuration

Settings loaded from `.env` (or environment variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `development` | Application environment |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `VECTOR_STORE_PROVIDER` | `qdrant` | Vector store backend |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model name |
| `CHUNK_SIZE` | `500` | Target chunk size in characters |
| `CHUNK_OVERLAP` | `50` | Overlap between consecutive chunks (`< CHUNK_SIZE`) |
| `OPENAI_API_KEY` | _(set in env)_ | Required for OpenAI embeddings |

Run `setup_logging()` once at application startup to configure structured logging (JSON or console).

## 🧪 Testing

```bash
# Run all unit tests
uv run pytest -q

# Run integration tests (requires live PostgreSQL)
uv run pytest -q --marker integration
```

56 tests total (36 previously existing + 20 new stage/builder tests).

## 📦 Dependencies

Core:
- `sqlalchemy`, `psycopg2-binary`, `alembic`, `pydantic-settings`, `python-dotenv`
- `pypdf`, `structlog`, `rich`

Indexing pipeline:
- Added `typer==0.15.4`, `rich==15.0.0` for CLI

Dev:
- `pytest>=9.1.1`

## 🔧 Development Notes

- `sync_deleted_payloads(active_source_ids)` soft-deletes payloads missing from source scans and flags associated chunks for purge
- `upsert_versioned_payload(payload)` handles v1 creation, vN+1 increments on content change, `UNCHANGED` skip
- Chunk IDs format: `{payload_id}::v{payload_version}::c{chunk_index}`
- Embedding fallback uses `hashlib.md5(text).hexdigest()` → deterministic 1536-dim vectors when `OPENAI_API_KEY` unset
- Database: PostgreSQL 16 with `pgvector` extension (`pgvector/pgvector:pg16` container `ragops_postgres`)
- Credentials (via docker inspect): `ragops:ragops@localhost:5432/ragops`

## ((()))