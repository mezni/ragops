# Step Tracker — RAG OPS

## Ingestion pipeline

| Step | Phase | Problem | Solution |
|---|---|---|---|
| Step 0.1: Project Bootstrap | Setup | Minimal setup required to bootstrap the project. | Added data generator (`scripts/generate_docs.py`) and initialized the project via `uv init` (`.venv` in place). |
| Step 1.1: Single PDF Ingestion Baseline | Ingestion | Single pipeline script with all ingestion stages (load, parse, chunk, embed). | Added `ingestion.py`. |
| Step 1.2: Text Cleaning & Metadata Extraction | Ingestion | PDF/HTML extraction leaves inline tags (`**`) and administrative header blocks inside text chunks. | Added `clean_text()` and `extract_frontmatter()`. |
| Step 1.3: Real Embedding Model | Ingestion | The pipeline uses numpy to generate random 1536-dim baseline vectors. | Replaced with a real embedding model via OpenRouter. |
| Step 1.4: Persistent Vector Store | Ingestion | `self.vector_store` is an in-memory dict (`Dict[str, EmbeddedChunk]`), so embeddings are lost when the script exits. | Integrated a ChromaDB `PersistentClient`; `upsert_to_vector_store()` persists `(id, embedding, document, metadata)` on disk and survives restarts. Added `search(query_text, top_k)`. |
| Step 1.5: Stage-Based Refactor | Ingestion | `RAGIndexingPipeline` became too big with all concerns in one class. | Split into single-purpose stages (`IngestionStage`, `ChunkerStage`, `EmbeddingStage`, `VectorStoreStage`); the pipeline is now a thin orchestrator with the same public API. |
| Step 1.6: Recursive Structure-Aware Chunking | Ingestion | Fixed-character slicing chops mid-word/mid-sentence, breaking semantic context. | Replaced with recursive splitting across paragraphs → lines → sentences → spaces; merges up to `chunk_size` with `chunk_overlap` windows (0 true mid-word cuts). |