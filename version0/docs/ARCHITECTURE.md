# Architecture & Technical Design Document (TDD)
## Versioned Enterprise RAG Platform

### 1. System Overview
The Versioned Enterprise RAG Platform is designed using a decoupled, pipeline-oriented architecture. The system cleanly separates Async Write Operations (Document Ingestion, Parsing, Chunking, Embedding) from Low-Latency Read Operations (Query Transformation, Hybrid Search, Reranking, Generation).

Plaintext
                                 ┌─────────────────────────┐
                                 │     Streamlit / Client  │
                                 └────────────┬────────────┘
                                              │ REST API / HTTP
                                              ▼
                                 ┌─────────────────────────┐
                                 │      FastAPI Gateway    │
                                 └──────┬────────────┬─────┘
                                        │            │
                   ┌────────────────────┘            └────────────────────┐
                   ▼                                                      ▼
     [ WRITE PIPELINE: Async Ingestion ]                   [ READ PIPELINE: Query & Search ]
                   │                                                      │
        ┌──────────┴──────────┐                                ┌──────────┴──────────┐
        │  Task Queue (Redis) │                                │ Query Transformer   │
        └──────────┬──────────┘                                └──────────┬──────────┘
                   │                                                      │
        ┌──────────▼──────────┐                                ┌──────────▼──────────┐
        │ Ingestion Worker    │                                │ Hybrid Search Engine│
        │ (Unstructured/Llama)│                                │ (Dense + BM25)      │
        └──────────┬──────────┘                                └──────────┬──────────┘
                   │                                                      │
        ┌──────────▼──────────┐                                ┌──────────▼──────────┐
        │ Chunk & Embedder    │                                │ Cross-Encoder Rerank│
        │ (OpenAI / HuggingF) │                                └──────────┬──────────┘
        └──────────┬──────────┘                                           │
                   │                                           ┌──────────▼──────────┐
                   │                                           │ LLM Synthesizer     │
                   │                                           └──────────┬──────────┘
                   │                                                      │
                   ▼                                                      ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                       Data Layer & Vector Store                             │
   │   - Qdrant (Dense Vectors + BM25 Sparse Index + Payload Version Filters)    │
   │   - PostgreSQL (Document Metadata, User Auth, Audit Logs)                   │
   └─────────────────────────────────────────────────────────────────────────────┘

### 2. Component Breakdown

#### 2.1 API Layer (src/rag_engine/api/)
Framework: FastAPI.
Responsibilities: Request validation, JWT token verification, RBAC filter extraction, routing requests to the ingestion queue or retrieval engine.

Key Endpoints:
- POST /api/v1/documents/upload — Accepts raw files, computes SHA-256 hash, triggers async processing task.
- POST /api/v1/query — Executes real-time RAG pipeline.
- PATCH /api/v1/documents/{payload_id}/version — Updates document version status (is_active: bool).

#### 2.2 Ingestion Engine (src/rag_engine/ingestion/)
Task Queue: Celery + Redis.
Document Loaders: Layout-aware parsers (Unstructured / PyMuPDF) that extract text, structural headers, and tables.
Chunking Strategy: Semantic Header Splitting with overlap (512 tokens max chunk size, 50-token overlap).
Metadata Attachment: Every chunk is enriched with:
```json
{
  "payload_id": "doc_8f9a2b",
  "version": "1.2.0",
  "tenant_id": "tenant_acme",
  "is_active": true,
  "page_number": 4,
  "created_at": 1773245967
}
```

#### 2.3 Retrieval & Query Pipeline (src/rag_engine/retrieval/)
Query Transformation (transforms.py): Rewrites natural language queries into optimized keyword search vectors or generates Hypothetical Document Embeddings (HyDE).

Hybrid Search Engine (search.py):
- Dense Vector Search: Qdrant HNSW index using Cosine Distance.
- Sparse Keyword Search: Qdrant Sparse Vectors (BM25 tokenization).
- Fusion: Reciprocal Rank Fusion (RRF) combines sparse and dense rank scores.

Filter Context: Query pre-filtering applied before distance calculation:
$$\text{Filter} = (\text{tenant\_id} == T) \land (\text{is\_active} == \text{True}) \land (\text{version} == V)$$

Cross-Encoder Reranker (rerankers.py): Re-scores top-50 hybrid candidates down to top-5 most relevant chunks using bge-reranker-large or Cohere Rerank API.

#### 2.4 Generation & Synthesis (src/rag_engine/generation/)
Context Assembly: Injects reranked chunks into versioned Jinja2 prompt templates.
Source Citation Engine: Mandates JSON schema or strict inline bracket formatting ([Source: chunk_id, page N]).
Fallback Logic: If maximum score after reranking is below threshold ($\tau < 0.35$), response immediately defaults to: "I am unable to answer based on the active documentation provided."

#### 3. Data Schema & Persistence

##### 3.1 Qdrant Vector Payload Schema
```json
{
  "id": "c1f7b0e2-7634-4a21-987a-b1089d3d4b68",
  "vector": {
    "dense": [0.012, -0.045, "... 1536 floats ..."],
    "sparse": {
      "indices": [102, 4501, 8920],
      "values": [0.45, 0.89, 0.12]
    }
  },
  "payload": {
    "text": "The maximum operating temperature for Module B is 180°C under normal load.",
    "payload_id": "doc_mod_b_spec",
    "version": "2.1.0",
    "tenant_id": "org_4512",
    "is_active": true,
    "doc_title": "Module B System Specs",
    "page_number": 12,
    "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}

##### 3.2 Relational Schema (PostgreSQL)
- **tenants** (tenant_id, name, created_at)
- **users** (user_id, tenant_id, email, role, hashed_password)
- **documents** (doc_id, tenant_id, filename, file_hash, active_version, status)
- **document_versions** (version_id, doc_id, version, storage_path, created_at, is_active)

#### 4. End-to-End Sequence Diagram
Plaintext
User            FastAPI          Redis/Celery      Qdrant DB      Cross-Encoder      LLM Service
 │                 │                  │                │               │                  │
 ├─ POST /query ──►│                  │                │               │                  │
 │                 │── Transform ────►│                │               │                  │
 │                 │   Query          │                │               │                  │
 │                 │                  │                │               │                  │
 │                 │── Hybrid Search (Dense+Sparse) ──►│               │                  │
 │                 │   [Filter: tenant, active_version]│               │                  │
 │                 │◄─ Return Top 50 Chunks ───────────│               │                  │
 │                 │                                                   │                  │
 │                 │── Rerank Top 50 Chunks ──────────────────────────►│                  │
 │                 │◄─ Return Top 5 Scored Chunks ─────────────────────│                  │
 │                 │                                                                      │
 │                 │── Prompt Assembly + Context Chunks ─────────────────────────────────►│
 │                 │◄─ Synthesized Answer + Citations ────────────────────────────────────│
 │                 │
 │◄─ Response ─────│

#### 5. Security & Isolation Controls
- **Multi-Tenant Boundaries**: Hard vector DB filters injected automatically at the API layer based on authenticated JWT claims.
- **Payload Version Rollbacks**: Inactivating a document version sets is_active=False across all related vectors in Qdrant in $O(1)$ time via a single payload update query.
- **Data at Rest & Transit**: Connections enforce TLS 1.3. Qdrant storage volume encrypted using AES-256.