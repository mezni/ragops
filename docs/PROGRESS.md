# Step Tracker — RAG Indexing Pipeline

## Step Tracker — RAG Ingestion

| Step | Phase | Problem | Solution |
|---|---|---|---|
| Step 0.1: Project Bootstrap | Setup | Minimal setup required to bootstrap the project. | Added data generator (`scripts/generate_docs.py`) and initialized the project via `uv init` (`.venv` in place). |
| Step 1.1: Single PDF Ingestion Baseline | Ingestion | Single pipeline script with all ingestion stages (load, parse, chunk, embed). | Added `ingestion.py` |
| Step 1.2: Text Cleaning & Metadata Extraction | Ingestion | PDF/HTML extraction leaves inline tags (`**`) and administrative header blocks inside text chunks. | Added `clean_text()` and `extract_frontmatter()`. |