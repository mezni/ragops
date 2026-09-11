# my_rag_platform
Modular RAG Platform with production-ready pipelines for document ingestion, retrieval, and evaluation.

## Structure
- `src/rag_engine/` — Core application package with ingestion, retrieval, generation, and evaluation modules
- `app/` — Streamlit user interface
- `tests/` — Unit and integration test suites
- `docs/` — Architecture and PRD documentation

## Quick Start
```bash
# Development
uv venv
uv pip install -e ".[dev]"

# Index documents
python -m rag_engine.ingestion.pipeline --source ./docs

# Run retrieval
python -m rag_engine.retrieval.pipeline --query "your question"

# Launch UI
streamlit run app/streamlit_app.py
```