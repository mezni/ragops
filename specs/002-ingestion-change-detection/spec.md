# Feature Specification: Ingestion & change detection

**Feature Branch**: `002-ingestion-change-detection`

**Created**: 2026-09-10

**Status**: Draft

**Input**: User description: "read docs/PLAN.md: Phase 1 — Ingestion & change detection"

## Overview

The pipeline must know *which* files on the filesystem changed since the last
run, **without parsing any of them yet**. Scanning compares the filesystem
against the previously-persisted `documents` state and classifies each file as
**new**, **modified**, or **deleted**. The result powers scan idempotence —
running `pipeline scan` twice on the same folder reports no changes the second
time (Phase 1 exit criterion, `docs/PLAN.md`).

This is the core understanding of the change-detection slice:
classification is done by file attributes (`content_hash`, `size`, `mtime`)
with no content inspection, and the `documents` state is the record of truth
throughout. No parsing, cleaning, chunking, or enrichment is implemented in
this slice.

## Scope

**In scope**: `documents` migration (Alembic), filesystem scanner with
streamed hashing, change detector (new/modified/deleted classification),
`pipeline scan` CLI that persists the classification and prints the result.

**Out of scope** (later phases per `docs/PLAN.md`): any parsing/cleaning of
file content, chunking, embedding, `pipeline db upgrade`-linked writes of
parsed data, or vector storage. Rename detection via content similarity is
explicitly deferred — a rename is seen as delete + new (same hash, different
path) and flagged as such in `modified`/`new` respectively.

## User Stories

### User Story 1 - Run a scan and see what changed (Priority: P1)

As a pipeline operator, I want to run `scan` against a source folder and get a
list of which files are new, modified, or deleted compared to the last run, so
that I can tell at a glance which documents need indexing or re-indexing.

**Why this priority**: P1 — "know which files changed" is the single most
critical capability of Phase 1: it is the foundation every later parsing
phase consumes. It is the "know which files changed" goal stated first in
`docs/PLAN.md` Phase 1, and it delivers the exit-criterion value (scan
idempotence) on its own: run once, run again, see "no changes".

**Independent Test**: `pipeline scan --root tests/fixtures` run twice on an
unchanged folder — second run reports no changes (exit `0`, empty
new/modified/deleted lists). This delivers the Phase 1 exit criterion by
itself.

**Acceptance Scenarios**:

1. **Given** a source folder with files, **When** I run `pipeline scan
   --root <folder>` twice without modifying anything, **Then** the second run
   reports exactly zero new / zero modified / zero deleted and exits `0`.
2. **Given** I edit one file (change content, size, or mtime), **When** I run
   `pipeline scan --root <folder>` again, **Then** that file appears in the
   `modified` list with its new `content_hash`/`size`/`mtime`.
3. **Given** the scanned folder is empty, **When** I run `pipeline scan
   --root <folder>`, **Then** it reports success (exit `0`) with all lists
   empty — an empty folder is never an error.

---

### User Story 2 - Classify changes correctly (new / modified / deleted) (Priority: P2)

As a pipeline operator, I want each file to be classified correctly against
the previous `documents` state so that only actually-changed files are
flagged for re-processing and no unchanged file is re-processed.

**Why this priority**: P2 — classification-by-metadata avoids re-parsing
unchanged files; this is the performance rationale (Constitution Article VII
— "already-done work ... is never repeated" — batching/streaming goal in
`docs/ARCHITECTURE.md` §5). This user story complements US1: US1 delivers the
detection result via the CLI, while US2 validates that the underlying
classification logic is correct against a seeded `documents` state.

**Independent Test**: seed `documents` with a known state
(fixture/migration), then run the classifier against a fixture folder —
assert each entry is classified `new` / `modified` / `deleted` exactly
according to the `documents` diff, independent of the CLI.

**Acceptance Scenarios**:

1. **Given** `documents` already contains a path, **When** the scanner finds
   the same path with identical `(content_hash, size, mtime)`, **Then** the
   file is classified `unchanged` (absent from all three lists).
2. **Given** `documents` contains path `A` but the scanner no longer sees it,
   **When** classification runs, **Then** path `A` is classified `deleted` and
   its `documents` row transitions to `status='deleted'` — the row is **never
   removed** (Constitution Article I §1).
3. **Given** the scanner finds path `B` that is not in `documents`, **When**
   classification runs, **Then** path `B` is classified `new`.

---

### User Story 3 - Scan is streamed and memory-safe (Priority: P3)

As an operator with large source folders, I want the scanner to compute file
hashes and attributes **in streaming fashion** (never loading a whole file
into memory) so that folders of any size can be scanned without exhausting
memory.

**Why this priority**: P3 — streaming protects Phase 4+ (real document
volumes); it does not change the classification result, so it is a
non-blocking robustness property (*external cost/latency* Article V).

**Independent Test**: run the scanner against a fixture directory and assert
that hashing is performed incrementally (a large multi-megabyte fixture is
hashed without buffering it fully in memory — verifiable by the
implementation's API signature and a memory-bound assertion in tests).

**Acceptance Scenarios**:

1. **Given** a folder with files of varying sizes, **When** the scanner runs,
   **Then** each file's `content_hash` is computed by streaming read (a fixed
   buffer, never the full file in memory).
2. **Given** a file whose read fails partway (permissions, mid-write),
   **When** the scanner runs, **Then** the file is skipped with a logged
   warning and the scan continues (a local failure never becomes a global
   failure — Constitution Article III).

---

## Edge Cases

- **File being written during scan**: a file whose `mtime`/`size` changes
  between the first attribute read and the hash computation is treated as
  unchanged and will be detected on the next run, never classified by a
  half-written state.
- **Unreadable file** (permissions, mid-write): logged as a warning and
  skipped without failing the whole run (Constitution Article III §2).
- **Symbolic link**: traversed or ignored according to config
  (`filesystem.follow_symlinks`), never a silent default either way
  (config-driven, Article II).
- **Empty folder / first ever run**: `documents` has no rows → all files are
  `new`; an empty folder yields success with empty lists, not an error.
- **File deleted between scan and persist**: treated as `deleted` and recorded
  with `status='deleted'`; the row is never physically removed.
- **Rename**: seen as `deleted` (old path) + `new` (new path); no content
  similarity detection in this slice (documented as a known v1 limitation).

## Key Entities

- **`documents`** (table, `documents.v1`): the persistent record of what the
  scanner last saw — `path` (unique), `content_hash`, `size`, `mtime`,
  `status` (`active`/`deleted`). Status `deleted` keeps delete history
  without losing rows (Constitution Article I §1).
- **FileRecord**: `path, size, mtime, content_hash` — the scanner's per-file
  output, streamed.
- **ScanResult**: `new`, `modified`, `deleted` — three disjoint lists
  produced by the change detector, persisted to `documents` and printed.
- **pipeline_runs / change-detection runner**: a scan is recorded as a run
  (traceability, Article II §3) with the config snapshot.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `pipeline scan --root <path>` command that
  recursively lists files, computing `content_hash` / `size` / `mtime` per
  file in streaming fashion (never whole file in memory).
- **FR-002**: System MUST filter filenames by the config's allowed
  extensions; files outside the filter are never classified.
- **FR-003**: System MUST classify each scanned file as `new`, `modified`, or
  `unchanged` by comparison of `(content_hash, size, mtime)` against the
  `documents` state; a path no longer present is classified `deleted`.
- **FR-004**: System MUST persist the classification atomically: new →
  insert row `status='active'`; modified → update hash/size/mtime; deleted →
  set `status='deleted'`; unchanged rows are left untouched. Every scan is
  recorded in `pipeline_runs` with its config snapshot (traceability,
  Article II §3).
- **FR-005**: System MUST be idempotent: a second scan of an unchanged folder
  produces zero `new` / `modified` / `deleted` entries and exit code `0`.
- **FR-006**: System MUST handle an empty folder and a first-ever run as
  success (all files `new`; empty folder = empty lists), never a failure.
- **FR-007**: System MUST NOT implement parsing/cleaning/chunking/embedding
  in this feature (Constitution Article VII scope discipline — those are
  later phases), and MUST NOT execute migrations at app startup (Article VI —
  migrations run explicitly via `pipeline db upgrade`).

### Success Criteria *(mandatory)*

- **SC-001**: A user runs `pipeline scan` on an unchanged folder twice; the
  second run reports zero changes. (Measurable: 0/0/0 lists, exit `0`.)
- **SC-002**: Editing a single file makes the next `pipeline scan` report that
  exact path in `modified` with updated attributes, and nothing else flagged.
- **SC-003**: Deleting a file makes the next scan report the path in
  `deleted`, and the `documents` row persists with `status='deleted'` (row
  count unchanged; nothing lost — Constitution Article I).
- **SC-004**: The scanner computes hashes in streaming mode with bounded
  memory, verified by tests that hash a large fixture without a full-file
  buffer.

## Assumptions

- Project uses `uv` (Python 3.12); dependencies already resolved in Phase 0
  (`docs/ARCHITECTURE.md` §7) — this feature adds no third-party deps.
- `config.yaml` is authoritative for `filesystem` scan options
  (`source_root`, allowed extensions, `follow_symlinks`), never hardcoded
  (Constitution Article II).
- `documents`/`pipeline_runs` migrations are authored explicitly in
  `migrations/` and applied via `pipeline db upgrade` (Article VI); the
  migration exists only because this feature owns the `documents` table.
- Deleted status is terminal for the source file only — a later phase may
  restore an active index from preserved history; that is out of this scope.
- Rename-without-change is out of scope (documented limitation, not a defect).
- Changes are detected by `(content_hash, size, mtime)` — a pure-content
  change that preserves size and mtime is detectable because `content_hash`
  differs; mtime is retained as a cheap pre-filter (per `docs/ARCHITECTURE.md`
  §5), not as the sole signal.
