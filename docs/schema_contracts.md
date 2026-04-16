# Splendor Schema Contracts

This document captures the draft schema layer that anchors Milestone 0 and the beginning of
Milestone 1. The implementation lives in `src/splendor/schemas/` and currently uses Pydantic v2.

## Design rules

- The repository filesystem is canonical.
- Structured records must be deterministic and validation-friendly.
- Markdown remains the primary human interface, but machine-readable state sits beside it.
- The current schema version is `1`.

## Source record

Stored today as JSON sidecars under `state/manifests/sources/`.

Current implementation fields:

- `schema_version`
- `kind: source`
- `source_id`
- `title`
- `source_type`
- `path`
- `checksum`
- `added_at`
- `status`
- `pipeline_version`
- `derived_artifacts`
- `linked_pages`
- `last_run_id`
- `review_state`
- `origin_url`
- `original_path`
- `source_ref`
- `source_ref_kind`
- `storage_mode`
- `storage_path`
- `materialized_at`
- `source_commit`

### Current source-record shape

The source record now splits three concerns explicitly:

- the canonical source the user wants tracked
- the storage mechanism Splendor used to make it available
- the current location from which ingest reads bytes

Implemented fields:

- `schema_version`
- `kind: source`
- `source_id`
- `title`
- `source_type`
- `source_ref`
- `source_ref_kind`
- `storage_mode`
- `storage_path`
- `checksum`
- `added_at`
- `status`
- `pipeline_version`
- `derived_artifacts`
- `linked_pages`
- `last_run_id`
- `review_state`
- `origin_url`
- `original_path`
- `materialized_at`

### Field semantics

- `source_ref`
  - Canonical source identifier.
  - Examples:
    - `docs/spec.md`
    - `/Users/alice/Desktop/notes.md`
    - `https://example.com/spec`
- `source_ref_kind`
  - One of:
    - `workspace_path`
    - `external_path`
    - `url`
    - `imported`
    - `stored_artifact`
- `storage_mode`
  - One of:
    - `none`
    - `copy`
    - `symlink`
    - `pointer`
  - Current runtime support:
    - `none` for workspace-backed sources
    - `copy` for workspace-backed and external local sources
    - `pointer` for workspace-backed sources
    - `symlink` for workspace-backed sources
- `storage_path`
  - Optional path under `raw/sources/` when Splendor materializes an artifact.
  - Pointer-backed sources use `raw/sources/<source_id>/pointer.json`.
  - Symlink-backed sources use `raw/sources/<source_id>/<filename>`.
- `materialized_at`
  - Timestamp indicating when `storage_path` was created or last refreshed.
- `source_commit`
  - Optional git commit SHA captured for clean tracked workspace files.

### Recommended default policy

Recommended defaults:

- workspace file inside repo:
  - `source_ref_kind: workspace_path`
  - `storage_mode: none`
  - `storage_path: null`
- external local file:
  - `source_ref_kind: external_path`
  - `storage_mode: copy`
- URL/imported source:
  - `storage_mode: copy` or `pointer`, depending on downloader semantics

### Compatibility note

Splendor currently supports both:

1. legacy manifests that only have `path` and are treated as copied-source records at read time
2. new manifests that write `source_ref`, `source_ref_kind`, `storage_mode`, `storage_path`,
   `materialized_at`, and `source_commit`

In this release:

- `path` remains required for compatibility
- copied sources still use `path` as the stored artifact path
- workspace-backed sources temporarily mirror `source_ref` into `path`
- no automatic manifest rewrite or schema-version bump is performed yet

## Knowledge page frontmatter

Minimal frontmatter contract for wiki pages:

- `schema_version`
- `kind`
- `title`
- `page_id`
- `status`
- `source_refs`
- `generated_by_run_ids`
- `last_reviewed_at`
- `confidence`
- `related_pages`
- `tags`

## Planning objects

Strict record contracts currently exist for:

- task
- milestone
- decision
- question

The implemented fields follow the product spec closely and reserve room for future markdown-backed
renderers and CLI creation commands.

## Queue and run records

The runtime contracts are now used by deterministic single-source ingestion.

- `QueueItemRecord` captures item lifecycle, retries, and leases.
- `RunRecord` captures pipeline inputs, outputs, warnings, and failures.

Current persisted locations:

- `state/queue/<job_id>.json`
- `state/runs/<run_id>.json`

## Current storage decision

The schemas are implemented as Python-native models first, with JSON sidecars for records that need
to exist before markdown renderers and richer file contracts are ready. That keeps the initial
implementation small while preserving deterministic validation and future compatibility with YAML
frontmatter or richer sidecar layouts.

The next storage-oriented schema change should preserve that philosophy: keep manifests
filesystem-native and explicit, but make source resolution policy first-class instead of baking a
copy-under-`raw/sources/` assumption into a single `path` field.
