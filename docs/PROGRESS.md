# Step Tracker — RAG Indexing Pipeline

## Step Tracker — RAG Ingestion

| Step | Phase | Problem | Solution |
|---|---|---|---|
| Step 0.1: Project Bootstrap | Setup | Minimal setup required to bootstrap the project. | Added data generator (`scripts/generate_docs.py`) and initialized the project via `uv init` (`.venv` virtual environment in place). |
| Step 1.1: Single PDF Ingestion Baseline | Ingestion | Single pipeline script with all ingestion stages (load, parse, chunk, embed). | Added `ingestion.py` — `load_file()` extracts text via `pypdf.PdfReader`; strict Pydantic models (`Document`, `TextChunk`, `EmbeddedChunk`); class-based pipeline (`RAGIndexingPipeline`) chaining `load_file()` → `chunk_document()` → `generate_embeddings()` → `upsert_to_vector_store()`. Tested successfully on `AW-BIL-001_billing_dispute_policy.pdf` (1536-dim vectors, `category: "billing"` metadata correct). |