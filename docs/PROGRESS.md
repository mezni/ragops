# Step Tracker — RAG Indexing Pipeline

## Step Tracker — RAG Ingestion

| Step | Phase | Problem | Solution |
|---|---|---|---|
| Step 0.1: Project Bootstrap | Setup | No executable skeleton — impossible to test a stage without shared config or a shared DB connection. | Skeleton created via `uv init`, `.venv` virtual environment in place. Still **pending**: `PipelineConfig` (Pydantic), SQLAlchemy engine with connection pooling, `docker-compose.yml` (Postgres+pgvector), migration 0 (`vector` extension). |
| Step 1.1: Single PDF Ingestion Baseline | Indexing | Only raw text documents were handled — `.pdf` files left the vector store empty. | `load_file()` extracts text via `pypdf.PdfReader`; strict Pydantic models (`Document`, `TextChunk`, `EmbeddedChunk`); class-based pipeline (`RAGIndexingPipeline`) chaining `load_file()` → `chunk_document()` → `generate_embeddings()` → `upsert_to_vector_store()`. Tested successfully on `AW-BIL-001_billing_dispute_policy.pdf` (1536-dim vectors, `category: "billing"` metadata correct). |