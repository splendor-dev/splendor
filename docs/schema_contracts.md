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

Core fields:

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

The runtime contracts are drafted now even though the execution engine is intentionally deferred.

- `QueueItemRecord` captures item lifecycle, retries, and leases.
- `RunRecord` captures pipeline inputs, outputs, warnings, and failures.

## Current storage decision

The schemas are implemented as Python-native models first, with JSON sidecars for records that need
to exist before markdown renderers and richer file contracts are ready. That keeps the initial
implementation small while preserving deterministic validation and future compatibility with YAML
frontmatter or richer sidecar layouts.
