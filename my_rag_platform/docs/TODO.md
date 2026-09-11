# TODO: Production Features Roadmap

## Phase 1: Must-Have for v1 Launch (Core Reliability & Security)
Goal: Prevent wrong/stale answers, secure data, and make answers verifiable.

- [x] Metadata & Multi-Tenant Filtering: Enforce strict payload filters (is_active, tenant_id) at the vector DB level so users never access unauthorized or soft-deleted data.
- [x] Inline Source Citations: Map generated answer sentences directly to retrieved chunk IDs (payload_id, version, page_number).
- [x] Document Versioning & Active Status: Maintain payload tags (version, is_active) to instantly toggle or roll back bad/outdated documentation.
- [x] Hybrid Search (Sparse + Dense): Combine dense vector search with BM25 keyword matching to handle exact identifiers, codes, and names.
- [x] Fallback & "I Don't Know" Handling: Tune prompts to gracefully reject out-of-context queries rather than hallucinating based on internal LLM parameters.
- [ ] Basic API Auth & Rate Limiting: Gate endpoints using API key/JWT authentication with simple request throttling to prevent misuse.

## Phase 2: Important for Scale (Performance & Operational Control)
Goal: Keep response times fast, handle heavy background tasks, and track system health.

- [ ] Background Task Queue: Offload heavy PDF parsing, chunking, and embedding generation to an async queue (e.g., Celery, Redis, Temporal).
- [x] Cross-Encoder Reranking: Fetch top_k=50 initial candidates and run a reranker (e.g., Cohere, bge-reranker-large) to select the top 3–5 chunks for the prompt context.
- [x] Tracing & Telemetry: Instrument end-to-end tracing (using Langfuse, Phoenix, or OpenTelemetry) to monitor latency across query transformation, vector retrieval, and LLM generation.
- [ ] Layout-Aware Document Parsing: Upgrade basic text splitters to layout-aware parsers for complex PDFs with tables and multi-column formats.
- [x] Automated CI Evaluation: Run offline evaluation benchmarks (Context Precision, Context Recall, Faithfulness) against a Golden QA dataset on pull requests.
- [x] PII Redaction & Input Guardrails: Scrub PII and sanitize prompt inputs before passing text to external embedding models or LLMs.

## Phase 3: Advanced Optimization (Cost Reduction & Fine-Tuning)
Goal: Lower token cost, minimize system latency, and handle edge cases automatically.

- [ ] Semantic Caching: Store semantically identical queries in a cache (e.g., Redis Vector Cache) to bypass LLM generation for frequent questions.
- [x] Query Transformation & Smart Routing: Dynamically rewrite messy user queries, decompose multi-part questions, or route trivial chats around retrieval entirely.
- [x] Document Deduplication & Hashing: Hash raw document contents (SHA-256) prior to parsing to avoid indexing identical files twice.
- [ ] Cost Tracking & Usage Budgets: Enforce per-tenant token spending caps with real-time alerting for high-cost queries.
- [x] Structured Output Validation: Enforce schema validation (e.g., Pydantic / JSON mode) for downstream machine consumption.