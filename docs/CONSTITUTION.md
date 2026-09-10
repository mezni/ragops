# Constitution — RAG Indexing Pipeline

## Preamble
This document establishes the guiding principles for the project. Any future design or implementation decision must conform to these rules or explicitly justify a derogation. Technical detail (schemas, config, flows) lives in `brief.md`; this document defines the rules that must remain true even when implementation changes.

---

## Article I — Nothing is lost, everything is traceable

1. No physical deletion of indexed source documents: a file disappearing from the filesystem moves to `status='deleted'`, it is never removed from the base.
2. Every chunk carries its provenance: source document hash, parser version, applied cleaning transformations, chunking strategy. A chunk without lineage is a chunk that cannot be debugged, and is therefore unacceptable.
3. Every pipeline run is recorded (`pipeline_runs`) with the exact configuration used. An untraceable run does not count as a production run.

---

## Article II — Anything that can change provider must be configurable, not hardcoded

1. The embedding provider, and later the enrichment providers (keywords, summary), are resolved at runtime from configuration validated by Pydantic — never imported hardcoded in business logic.
2. Any external integration (new provider, new document source) implements behind an already-defined interface, without modifying the rest of the pipeline.
3. A provider or model change is a traceable event (`enrichment_version`, `parser_version`, `index_versions`), never a silent data modification of existing records.

---

## Article III — A local failure never becomes a global failure

1. Each document is processed in its own transaction: parse → clean → chunk → enrich → embed → write. It is fully indexed or not at all.
2. A document failure (corrupt, timeout, API error) is isolated, logged with its cause, and does not interrupt processing of other documents in the run.
3. No run executes concurrently with another (mandatory application-level advisory lock).

---

## Article IV — The vector index can always be rolled back

1. Any reconstruction or embedding strategy change creates a new index version, never an in-place modification of the active version.
2. Rollback is a pointer switch operation, not a data rewrite operation.
3. Evaluations are attached to an index version, not just a run, enabling rollback decisions based on comparable metrics.

---

## Article V — Cost and latency are design constraints, not optimization details

1. Any call to an external paid provider (embedding, LLM) is batched by default, never chunk-by-chunk.
2. Already-done work on unchanged content (same hash, same treatment version) is never repeated.
3. Any costly step (LLM enrichment) is optional and disableable without breaking the data schema — fields exist, execution is conditional.

---

## Article VI — Nothing goes to production without test

1. Every pipeline step (parsers, cleaning, chunker) has independent unit tests not dependent on other steps.
2. A valid golden document set validates the end-to-end pipeline before any deployment.
3. No schema migration or default configuration change is merged without CI passing (migrations + tests + Docker build).

---

## Article VII — Scope discipline

1. Immediate project scope is limited to: per-document resilience + transactional writing, `pipeline_runs` table, embedding batching, tests and CI.
2. Any other capacity identified (advanced observability, Postgres maintenance, Streamlit dashboard, security hardening) is noted in the backlog of `brief.md`, not implemented prematurely.
3. A backlog feature becomes immediate scope only after an explicit decision, not through progressive drift during implementation.

---

## Amendments
Any modification of this document must be a conscious decision, not an accidental consequence of an implementation choice. Added here with date and justification.

- *(no amendments yet)*
