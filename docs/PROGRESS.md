# Step Tracker — RAG Indexing Pipeline

A phased engineering ledger tracking every problem, design choice, and bottleneck across the development lifecycle. Each new step (Step 0.1, Step 0.2, Step 1.1, ...) is copied from the template below, aligned with the `execution_plan.md` phases.

## Template (copy for each new step)

| Field | Details |
|-------|---------|
| **Step ID & Name** | `Step X.Y: <short name>` |
| **Phase** | `<Setup / Indexing / Resilience / Testing / ...>` |
| **Files Modified** | `<created or modified files>` |
| **Problem** | `<why this step is necessary>` |
| **Approach** | `<design decision + tech used>` |
| **Result** | `<target outcome → result obtained>` |
| **Next** | `<next step or known blocker>` |

---

## Current Steps

### Step 0.1: Project Bootstrap

| Field | Details |
|-------|---------|
| **Step ID & Name** | Step 0.1: Project Bootstrap |
| **Phase** | Setup |
| **Files Modified** | `pipeline/config.py`, `core/db.py`, `docker-compose.yml`, `migrations/versions/0001_init.py` |
| **Problem** | No executable skeleton — impossible to test a stage without shared config or DB connection. |
| **Approach** | PipelineConfig (Pydantic) as the single source of config; SQLAlchemy engine with connection pooling; migration 0 enables the vector extension. |
| **Result** | Target: `docker-compose up` starts Postgres+pgvector, `pipeline db upgrade` runs without errors. Achieved: `uv init` + venv creation done; Pydantic config, SQLAlchemy engine, docker-compose, and migration 0001 *(pending)* |
| **Next** | Filesystem change detection (Step 1.1 — Phase 1 of `execution_plan.md`) |

### Step 1.1: Single PDF Ingestion Baseline

| Field | Details |
|-------|---------|
| **Step ID & Name** | Step 1.1: Single PDF Ingestion Baseline |
| **Phase** | Discovery |
| **Files Modified** | `ingestion.py` |

**1. Core Problem**

- **Symptom:** Need to extract raw text and create valid schema chunks from binary PDF files (`AW-BIL-001_billing_dispute_policy.pdf`).
- **Production Impact:** Customer policy files are stored in `.pdf` format; failure to parse binary PDFs leaves the vector store empty.
- **Target Metric:** Successfully parse PDF, slice into validated `TextChunk` models, and verify non-empty text content.

**2. Solution Design**

- **Approach:** Integrate `pypdf` page extraction into a class-based pipeline using Pydantic data schemas for strict type safety.
- **Trade-offs:** Fixed-size character splitting is simple and fast, but may cut mid-sentence across page boundaries.
- **Tech Stack:** Python, pydantic, pypdf, numpy.

**3. Implementation**

- `ingestion.py` Updates: Added `load_file()` to handle path loading and PDF text extraction. Created `Document`, `TextChunk`, and `EmbeddedChunk` Pydantic models.
- **Code Blueprint:** `load_file()` checks file extensions and uses `pypdf.PdfReader` to extract page text before passing it to `chunk_document()`.

**4. Verification**

- **Test Scenario:** Ran `ingestion.py` targeting `data/raw/billing/AW-BIL-001_billing_dispute_policy.pdf`.
- **Pass Criteria:** `pipeline.run()` returns $>0$ `EmbeddedChunk` objects with extracted text and correct metadata (`category: "billing"`).
- **Actual Result:** Successfully extracted and indexed PDF text into chunk models with 1536-dimensional baseline vectors.

**5. Retrospective**

- **Engineering Takeaway:** Pydantic models ensure strict schema adherence during data transformation, preventing corrupted metadata down the line.