# Architecture Documentation
## Versioned RAG Platform

### 1. High-Level Overview
A modular Retrieval-Augmented Generation (RAG) platform built with Python, Streamlit, Qdrant, and PostgreSQL. The system decouples ingestion, indexing, retrieval, and evaluation into independent pipeline stages that compose via a generalized pipeline engine.

```
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│   Document Store   │     │   Vector Store     │     │   Evaluation API   │
│  (Postgres + pgvec)│     │   (Qdrant + pgvec) │     │  (Metrics + Reports)│
└───────┬────────────┘     └───────┬────────────┘     └───────┬────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│   Ingestion Layer  │     │   Retrieval Layer  │     │   UI Layer         │
│  (Streamlit + API) │     │  (CLI + Web UI)    │     │  (Streamlit Pages)│
└───────┬────────────┘     └───────┬────────────┘     └───────┬────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Core Engine                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │
│  │ PipelineStage[I,O] │  │ GeneralizedPipeline[I,O]│  │ EvaluationPipeline │  │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │
│           │                   │                   │                     │
│           └───────┬───────────┘                   └───────┬─────────────┘
│                     │                                 │
│          build_indexing_pipeline()                run_eval(dataset)    │
│                     │                                 │
│          run_indexing_pipeline()                  _compute_summary() │
│                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Component Diagram

#### 2.1 Core Infrastructure (`core/`)
- `config.py` — Pydantic-settings based environment configuration (`ENV`, `DATABASE_URL`, `OPENAI_API_KEY`, `CHUNK_SIZE`, `CHUNK_OVERLAP`)
- `logging.py` — structlog-based JSON/console logging; `setup_logging()` call at startup
- `pipeline.py` — `PipelineStage[I, O]` base class with `stage_name` and `execute(input_data, context)`; `GeneralizedPipeline[I, O]` that threads data through ordered stages
- `database.py` — `DatabaseManager` ORM models (`RawPayloadModel`, `TextChunkModel`, `DocumentModel`) + `upsert_versioned_payload(raw_payload)`, `sync_deleted_payloads(active_source_ids)`

#### 2.2 Indexing Pipeline (`indexing/`)
- `stages/ingestion.py` — `IngestionStage: List[RawPayload] → List[Document]` via `DatabaseManager.upsert_versioned_payload(raw_payload)` + parser routing (PDF/Markdown/Text) + `sync_deleted_payloads(active_source_ids)` flagging `is_purged=True` on chunks
- `stages/chunking.py` — `ChunkingStage: List[Document] → List[TextChunk]` sliding window, `chunk_id = "{payload_id}::v{payload_version}::c{idx}"`
- `stages/embedding.py` — `EmbeddingStage: List[TextChunk] → List[EmbeddedChunk]` OpenAI when key set, else deterministic 1536-dim MD5 fallback
- `builder.py` — `build_indexing_pipeline()` → `GeneralizedPipeline[List[RawPayload], List[EmbeddedChunk]]` with `name="VersionedIndexingPipeline"`

#### 2.3 Retrieval Pipeline (`retrieval/`)
- `stages/query_transform.py` — `QueryTransformStage: rewrite`/`hyde` modes; `HyDE` falls back to original query when `OPENAI_API_KEY` absent
- `stages/retriever.py` — `RetrieverStage: embeds query` + `vector_store.search(query_vector, top_k, filters)` with Qdrant payload filtering (`is_active=True`, `is_deleted=False`)
- `stages/reranker.py` — `RerankerStage: Cross-Encoder reranking`; `top_n` limit; fallback slice
- `stages/generator.py` — `GeneratorStage: LLM answer synthesis`; OpenAI when key set, else deterministic fallback
- `stages/models.py` — `Query`, `RetrievedChunk`, `RetrievalResult`, `SynthesizedResponse`
- `builder.py` — `build_retrieval_pipeline()` composing 4 stages; `run_indexing_pipeline()` entry point
- `vector_store/qdrant.py` — `QdrantAdapter` with `_build_payload_filter` (`is_active=True`, `is_deleted=False`) + `search(query_vector, top_k, filters) → List[RetrievedChunk]`

#### 2.4 Evaluation (`evaluation/`)
- `metrics/retrieval_eval.py` — `evaluate_retrieval(retrieved_chunk_ids, expected_chunk_ids) → Dict[str, float]` (hit_rate, mrr, context_precision, context_recall)
- `metrics/generation_eval.py` — `evaluate_generation(generated_answer, retrieved_contexts, ground_truth) → Dict[str, float]` (faithfulness, answer_relevance)
- `metrics/__init__.py` — Exports `evaluate_retrieval`, `evaluate_generation`
- `builder.py` — `EvaluationPipeline` with `run_eval(dataset_path) → Dict[str, Any]` and `_compute_summary(results) → Dict[str, float]`
- `reporters/console.py` — `ConsoleReporter.print_report(eval_output)` with summary + per-case tables
- `reporters/json_reporter.py` — `JSONReporter.export(eval_output, output_path)` for CI/CD JSON export
- `datasets/ground_truth.json` — 2 QA test cases with `expected_payload_id`, `expected_context_chunks`, `ground_truth_answer`
- `datasets/synthetic_gen.py` — `generate_synthetic_dataset(chunks, output_file)` auto-generator

#### 2.5 Application UI (`app/`)
- `streamlit_app.py` — Page config, global theming, main entry point
- `components/__init__.py` — Exports 5 reusable UI components
- `components/sidebar.py` — Pipeline controls (transform mode, top_k, rerank_top_n) + payload version filters
- `components/chat.py` — `render_chat_message(role, content)` + `render_cited_chunks(cited_chunks)` expander
- `components/admin.py` — `render_document_status_table(documents)` + `render_version_toggle(payload_id, current_version)`
- `pages/1_🔍_Search_&_Chat.py` — RAG interactive chat interface: sidebar → query → retrieval → answer + citations
- `pages/2_📂_Document_Manager.py` — Document upload form + ingestion trigger + document status table + version toggle actions
- `pages/3_📊_Evaluation.py` — Dataset path input → `run_eval()` → metric cards (precision/recall/faithfulness/MRR) → itemized JSON results

#### 2.5 CLI (`main.py`)
- Typer-based CLI with commands: `index`, `migrate`, `query`, `evaluate`, `ui`
- All commands verified end-to-end against live PostgreSQL

### 3. Data Flow

#### 3.1 Indexing Flow
```
Raw Payloads
    │
    ▼
IngestionStage: format routing (PDF→PDFParser, MD→MarkdownParser, TXT→TextParser)
    │
    ▼
DatabaseManager.upsert_versioned_payload(): v1 on new, vN+1 on change, skip if unchanged
    │
    ▼
ChunkingStage: sliding window → chunk_id = "{payload_id}::v{payload_version}::c{idx}"
    │
    ▼
EmbeddingStage: OpenAI embeddings or MD5 1536-dim fallback
    │
    ▼
Persist to PostgreSQL (raw_payloads, documents, text_chunks tables)
    │
    ▼
Index into Qdrant (vector embeddings + payload metadata: is_active, is_deleted, version)
```

#### 3.2 Retrieval Flow
```
User Query
    │
    ▼
QueryTransformStage: rewrite/hyde mode
    │
    ▼
RetrieverStage: embed query → Qdrant search with payload filter (is_active=True, is_deleted=False)
    │
    ▼
RerankerStage: Cross-Encoder re-score top-n candidates
    │
    ▼
GeneratorStage: LLM answer synthesis or deterministic fallback
    │
    ▼
Return: answer + cited_chunks (with chunk_id, payload_version, score, rerank_score, chunk_text)
```

#### 3.3 Evaluation Flow
```
Dataset JSON (ground_truth.json or synthetic)
    │
    ▼
EvaluationPipeline.run_eval(): iterate test cases
    │
    ▼
For each case: build_retrieval_pipeline() → run(query_obj) → response
    │
    ▼
extract: retrieved_chunk_ids, retrieved_texts, generated_answer
    │
    ▼
evaluate_retrieval(retrieved_chunk_ids, expected_chunk_ids) → metrics
    │
    ▼
evaluate_generation(generated_answer, retrieved_texts, ground_truth) → metrics
    │
    ▼
_compute_summary(results) → mean_mrr, mean_hit_rate, mean_context_precision, mean_context_recall, mean_faithfulness, mean_answer_relevance
    │
    ▼
ConsoleReporter.print_report() or JSONReporter.export() → CI/CD output
```

### 4. Database Schema (PostgreSQL + pgvector)

| Table | Key Columns | Constraints |
|-------|-------------|-------------|
| `raw_payloads` | `payload_id`, `version`, `is_active`, `is_deleted`, `raw_content`, `content_type`, `metadata` | PK: `(payload_id, version)` via `pk_raw_payloads_id_version` |
| `documents` | `id`, `filename`, `payload_id` (FK), `is_active` | Soft-deletion only |
| `text_chunks` | `chunk_id`, `payload_id`, `version`, `chunk_index`, `chunk_text`, `is_purged` | PK implicit; `is_purged` added via migration `3d9845bc5b97` |

- Composite PK on `raw_payloads`: `(payload_id, version)` → `pk_raw_payloads_id_version`
- `is_deleted` flag: soft-delete only, no hard `DELETE` statements
- `is_purged` flag: chunks of deleted payloads marked for purge; not physically removed until compaction

### 5. API Surface (Python Imports)

#### 5.1 Core
```python
from core.pipeline import PipelineStage, GeneralizedPipeline
from core.database import DatabaseManager, RawPayloadModel, TextChunkModel, DocumentModel
```

#### 2. Indexing
```python
from indexing.builder import build_indexing_pipeline
from indexing.stages.ingestion import IngestionStage
from indexing.stages.chunking import ChunkingStage
from indexing.stages.embedding import EmbeddingStage
```

#### 3. Retrieval
```python
from retrieval.builder import build_retrieval_pipeline
from retrieval.stages.query_transform import QueryTransformStage
from retrieval.stages.retriever import RetrieverStage
from retrieval.stages.reranker import RerankerStage
from retrieval.stages.generator import GeneratorStage
from retrieval.stages.models import Query, RetrievedChunk, RetrievalResult, SynthesizedResponse
from retrieval.vector_store.qdrant import QdrantAdapter
```

#### 4. Evaluation
```python
from evaluation.builder import EvaluationPipeline
from evaluation.metrics.retrieval_eval import evaluate_retrieval
from evaluation.metrics.generation_eval import evaluate_generation
from evaluation.reporters.console import ConsoleReporter
from evaluation.reporters.json_reporter import JSONReporter
```

#### 5. App UI
```python
from app import EvaluationPipeline  # or just: streamlit run main.py ui
from app.components.sidebar import render_sidebar
from app.components.chat import render_chat_message, render_cited_chunks
from app.components.admin import render_document_status_table, render_version_toggle
```

### 6. CLI Commands

```bash
# Indexing
python main.py index --source-dir ./data/docs

# Migrations
python main.py migrate --message "initial_schema"

# Query
python main.py query "What is RAG?" --top-k 5

# Evaluation
python main.py evaluate --dataset ./evaluation/datasets/ground_truth.json

# UI
python main.py ui
```

### 7. State Management

| Component | State | Persistence |
|-----------|-------|-------------|
| `raw_payloads` table | `(payload_id, version, is_active, is_deleted)` | PostgreSQL |
| `text_chunks` table | `(chunk_id, is_purged)` | PostgreSQL |
| Qdrant vector index | embedding vectors + payload filters | Qdrant container |
| Streamlit session_state | chat messages, pipeline settings | In-memory (process-local) |
| Environment variables | `.env` config | File-based |

### 8. Error Handling

- **Parser failures** (`FileNotFoundError`, `pdftotext` errors) → logged via structlog, skipped gracefully
- **Embedding failures** (no `OPENAI_API_KEY`) → deterministic MD5 fallback vectors; warning logged
- **Pipeline stage failures** → `GeneralizedPipeline.run()` raises; caught in Streamlit with `st.error()`
- **Qdrant connection loss** → `QdrantAdapter.search()` raises connection error; caught at CLI/UI boundary
- **Evaluation failures** (missing dataset, malformed JSON) → `try/except` in `run_eval()`; user-facing `st.error()`

### 9. Extensibility Points

| Extension Point | Hook | Example |
|----------------|------|---------|
| New pipeline stage | Subclass `PipelineStage[I, O]`, implement `execute(input_data, context)` | `MyStage.execute()` → return transformed data |
| New embedding model | Modify `EmbeddingStage.execute()` or set `OPENAI_API_KEY` | `OpenAIEmbeddings(model="text-embedding-3-large")` |
| New metric | Subclass `BaseMetric`, implement `evaluate()` | `FaithfulnessMetric.evaluate()` → return `MetricScore` |
| New reporter | Implement `export(eval_output, path)` or `print_report(eval_output)` | `CSVReporter.export()` → `csv.writer` |
| New dataset format | Add parser in `parsers/` + route in `IngestionStage` | `CSVParser` → `csv.reader` |

### 10. Deployment Checklist

- [ ] PostgreSQL 16 + pgvector container running (`docker-compose up`)
- [ ] Qdrant container running (`pgvector/pgvector:pg16`)
- [ ] `.env` file with `DATABASE_URL`, `OPENAI_API_KEY` (optional, for fallback), `ENV=production`
- [ ] `uv sync` or `pip install -r requirements.txt` installed
- [ ] `alembic upgrade head` applied (migrations: baseline + `3d9845bc5b97` for `is_purged`)
- [ ] `uv run pytest -q` passes (77/77 tests)
- [ ] Streamlit launches: `python main.py ui` → three pages navigable
- [ ] `python main.py index --source-dir ./data/docs` indexes test documents
- [ ] `python main.py evaluate --dataset ./evaluation/datasets/ground_truth.json` runs without error
- [ ] `python main.py query "test question"` returns answer with cited chunks