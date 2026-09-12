# Step Tracker — RAG Indexing Pipeline

## Step Tracker — RAG Ingestion

| Step | Phase | Problem | Solution |
|---|---|---|---|
| Step 0.1: Project Bootstrap | Setup | Minimal setup required to bootstrap the project. | Added data generator (`scripts/generate_docs.py`) and initialized the project via `uv init` (`.venv` in place). |
| Step 1.1: Single PDF Ingestion Baseline | Ingestion | Single pipeline script with all ingestion stages (load, parse, chunk, embed). | Added `ingestion.py` |
| Step 1.2: Text Cleaning & Metadata Extraction | Ingestion | PDF/HTML extraction leaves inline tags (`**`) and administrative header blocks inside text chunks. | Added `clean_text()` and `extract_frontmatter()`. |
| Step 1.3: Real Embedding Model | Ingestion | The pipeline currently uses numpy to generate embeddings (random 1536-dim baseline vectors). | Replace it with an embedding model (e.g., Sentence-Transformers / OpenAI embeddings). |
| Step 1.4: Persistent Vector Store | Ingestion | `self.vector_store` uses a Python dictionary (`Dict[str, EmbeddedChunk]`) — all stored embeddings are lost from RAM when the script finishes. | Integrated ChromaDB `PersistentClient` (`data/processed/chroma`) directly into the pipeline; `upsert_to_vector_store()` now persists `(id, embedding, document, metadata)` on disk and survives process restarts. Added `search(query_text, top_k)` for retrieval. |
| Step 1.5: Stage-Based Refactor | Ingestion | `RAGIndexingPipeline` becomes too big (loading, cleaning, chunking, embedding, storage all in one class). | Split into single-purpose stage classes in the same file: `IngestionStage`, `ChunkerStage`, `EmbeddingStage`, `VectorStoreStage`. `RAGIndexingPipeline` is now a thin orchestrator that composes the stages and keeps the same public API. |