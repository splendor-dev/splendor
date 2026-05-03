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
- `generated_by_run_ids`
- `last_run_id`
- `review_state`
- `reviewed_at`
- `reviewed_by`
- `origin_url`
- `original_path`
- `source_ref`
- `source_ref_kind`
- `storage_mode`
- `storage_path`
- `materialized_at`
- `source_commit_capture`
- `source_commit`
- `source_class`
- `source_labels`
- `discovered_by`
- `provenance_links`

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
- `generated_by_run_ids`
- `last_run_id`
- `review_state`
- `reviewed_at`
- `reviewed_by`
- `origin_url`
- `original_path`
- `materialized_at`
- `source_commit`
- `source_class`
- `source_labels`
- `discovered_by`
- `provenance_links`

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
- `source_commit_capture`
  - Nullable persisted intent for git provenance capture:
    - `true` means commit capture was explicitly requested for registration and refresh
    - `false` means commit capture was explicitly disabled
    - `null` means use the workspace `sources.capture_source_commit` default
  - Legacy manifests without this field preserve positive capture intent when `source_commit` is
    already populated.
- `source_commit`
  - Optional git commit SHA captured for clean tracked workspace files.
- `source_class`
  - Deterministic repo-scan classification.
  - One of:
    - `code`
    - `documentation`
    - `configuration`
    - `other`
- `source_labels`
  - Deterministic path-role labels such as `test`, `example`, `automation`, and
    `agent-instructions`.
- `discovered_by`
  - Optional registration origin marker.
  - One of:
    - `manual`
    - `repo_scan`

### Source lifecycle commands

- `splendor add-source <path>` preserves single-file registration behavior.
- `splendor add-source --glob "pattern"` expands matching files in deterministic path order.
- `splendor add-source --dir path` registers direct child files in deterministic path order.
- Newly registered CLI sources are handed to the existing ingest queue as `ingest-<source-id>`
  records; already registered sources are reported without creating duplicate work.
- `splendor source list` and `splendor source lookup [query]` provide a readable title/path to
  `source_id` mapping. They are lookup surfaces only and do not rename canonical source IDs or
  generated `wiki/sources/src-...md` pages.
- `splendor source refresh <source-id|title|path>` resolves the tracked workspace or external path,
  compares current bytes to the manifest checksum, registers changed content as a new canonical
  source version, preserves `source_commit_capture` intent, and queues ingest through the same queue
  handoff used by `add-source`.
- `splendor source freshness` is a non-mutating preview over curated source manifests. It reports
  path-first freshness state for workspace-backed canonical source refs, including unchanged,
  changed, missing, and unsupported statuses, manifest/current checksums where available, source
  IDs, titles, manifest paths, historical versions for paths covered by a current manifest, and
  exact next commands for changed sources.
- `splendor source freshness --json` emits the same preview for machine handoff. `--report PATH`
  writes only an explicit freshness report JSON, with relative report paths resolved from the
  current working directory; the default command writes no source manifests, wiki pages, derived
  artifacts, queue records, run records, or reports.
- Refresh uses the queue ledger directly, so active leases remain protected and dead-lettered jobs
  still require `splendor queue retry <job-id>` or `splendor repair ingest <source-id>`.
- `splendor suggest-next [goal]` is a read-only handoff view over existing deterministic state. It
  does not create planning records, queue jobs, manifests, wiki pages, run records, or reports.
  Human output is path-first where possible; `--json` emits ranked action objects with category,
  priority, title, reason, command, path, source ID/source ref, and planning/page record IDs when
  available.
- Suggested actions are derived from source freshness, queue operator state, invalid/stale/
  contested/review-needed wiki pages, ingested sources missing maintained synthesis follow-up,
  active planning records, recent lint/health reports, and optional goal query matches.
- Text-bearing PDF sources are routed through source-type dispatch during ingest. The source
  manifest keeps the same `source_ref`, `source_ref_kind`, and `storage_mode` contract as
  text-native sources, while extracted text artifacts are recorded in `derived_artifacts`.
- Image sources and image-only PDFs use the same source registration and resolver contract. OCR is
  optional and explicitly configured; successful OCR-derived text is recorded in
  `derived_artifacts` without changing the canonical source identity. Sidecar OCR inputs are
  tracked through metadata artifacts so no-op ingest can detect sidecar checksum drift.

### Derived artifacts

`derived_artifacts` stores repo-relative paths to repairable machine-generated artifacts derived
from the source. Current runtime support writes parsed text from text-bearing PDFs to
`derived/parsed/<source-id>.txt`, configured OCR text to `derived/ocr/<source-id>.txt`, and OCR
sidecar metadata to `derived/metadata/<source-id>.ocr.json`; lint and health validate that listed
artifacts are repo-relative, remain under `derived/`, and exist on disk.

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
   `materialized_at`, `source_commit_capture`, `source_commit`, and optional repo-scan
   classification fields

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
- `review_state`
- `source_refs`
- `generated_by_run_ids`
- `last_generated_at`
- `last_reviewed_at`
- `confidence`
- `related_pages`
- `tags`
- `provenance_links`
- `contradictions`

Current runtime behavior:

- `splendor add-topic "Title"` writes maintained topic pages under `wiki/topics/<slug>.md` with
  `kind: topic`, `page_id: topic-<slug>`, `status: active`, `review_state: draft`, optional tags,
  and optional source refs
- `splendor add-topic --template default|research-synthesis|issue-tracker` uses deterministic
  markdown scaffolds; templates do not generate source-summary content or LLM-authored synthesis
- `splendor wiki rebuild-index` rewrites `wiki/index.md` from validated wiki page frontmatter and
  does not mutate generated source-summary pages
- source-summary pages written by `splendor ingest` now use `review_state: machine-generated`
- those pages persist `last_generated_at`
- those pages persist structured provenance links back to the source manifest, ingest run, and
  source-content path actually read
- readable workspace-backed text summaries default to a policy-driven `excerpt` extract that
  prefers claim-bearing sections before falling back to a bounded opening excerpt
- copied, external, parsed PDF, and OCR-derived sources keep fuller extracts by default because the
  generated page or derived artifact is often the easiest local review surface
- human-facing source-summary markdown renders source paths/source files before source IDs, while
  frontmatter and state records keep canonical source IDs as the durable linkage contract
- when contradiction review finds explicit conflicts, both involved source-summary pages switch to
  `review_state: contested`
- contested pages persist structured contradiction annotations with linked review-task IDs and
  evidence snippets for both sides of the conflict

## Planning objects

Strict record contracts currently exist for:

- task
- milestone
- decision
- question

The implemented fields follow the product spec closely and reserve room for future markdown-backed
renderers and CLI creation commands.

Task records now also reserve:

- `page_refs`
- `run_refs`

Those fields let contradiction-review tasks carry explicit links back to the affected wiki pages
and the ingest run that surfaced the conflict.

## Query snapshots

The latest saved query snapshot lives at `state/queries/last-query.json`.

Current implementation fields:

- `schema_version`
- `query`
- `filters`
  - `tags`
  - `source_id`
  - `source_ids`
- `summary`
- `match_count`
- `created_at`
- `matches`

Query matches preserve rank, score, class/kind, record identity, path, status/review state, snippet,
source refs, generated run IDs, provenance links, contradiction counts, review task IDs, and tags.
When a source filter is provided by readable path and multiple content-addressed source versions
share that path, `source_id` stores the primary resolved source ID and `source_ids` stores every
matching source ID used for the filter.
`splendor query --no-save` preserves query output behavior but does not update this snapshot.

## Queue and run records

The runtime contracts are now used by deterministic single-source ingestion.

- `QueueItemRecord` captures item lifecycle, retries, backoff scheduling, dead-letter state, and
  leases.
- `RunRecord` captures pipeline inputs, outputs, warnings, and failures.

Current persisted locations:

- `state/queue/<job_id>.json`
- `state/runs/<run_id>.json`

Queue status values are `pending`, `leased`, `done`, `failed`, and `dead_letter`. Failed records may
carry `next_attempt_at` to defer the next automatic `splendor ingest --pending` retry. Dead-letter
records preserve `last_error` and require an explicit `splendor queue retry <job-id>` or
`splendor repair ingest <source-id>` action.

Run records now reserve explicit provenance fields beside the original generic refs so later
pipeline steps can answer questions like "which page did this run generate?" without parsing
free-form `output_refs` values:

- `source_ids`
- `page_ids`
- `page_refs`
- `contradiction_ids`
- `task_ids`
- `provenance_links`

Current runtime behavior:

- ingest populates `source_ids` as soon as the run is created
- successful ingest runs populate `page_ids`, `page_refs`, and structured generated-page
  provenance while preserving `input_refs` and `output_refs` for compatibility
- contradiction-reviewed ingest runs also persist the contradiction IDs and linked review-task IDs
  created or touched during that run
- failed runs retain only the source/input-side structured provenance that was actually known at
  failure time

## Repo scan

The CLI now includes `splendor repo scan` for deterministic repo-native discovery.

Current runtime behavior:

- bare `splendor repo scan` is a non-mutating candidate preview
- preview mode writes no source manifests, wiki pages, derived artifacts, queue records, run
  records, or reports
- `--json` emits machine-readable preview JSON to stdout
- `--report PATH` writes only an explicit discovery report JSON
- candidates include repo-relative paths, source classes, labels, status, and already-curated
  source identity when a workspace-backed source manifest already tracks the path
- ignored paths include a deterministic reason such as `managed_or_transient`, `gitignore`,
  `include_patterns`, `exclude_patterns`, or `class_filter`
- mutating registration requires `--apply` plus `--class ...` or `--all`
- large apply runs require `--allow-large-apply` after preview review
- scan honors `sources.include_patterns`, `sources.exclude_patterns`, and
  `sources.repo_scan_default_classes` from `splendor.yaml`
- scan skips Git-ignored files, Splendor-managed directories, dependency directories, and
  transient cache/build directories by default

## Repo refresh

The CLI now includes `splendor repo refresh` for deterministic repo-aware wiki maintenance.

Current runtime behavior:

- run safe repo discovery without registering new source manifests by default
- write machine-generated architecture and topic pages for repository structure and curated source
  linkage
- link generated pages to already-curated source IDs through frontmatter and provenance links
- update the wiki index and log idempotently
- mutating scan registration requires `repo refresh --apply-scan` plus `--class ...` or `--all`;
  large apply runs also require `--allow-large-apply`

## Review config

The workspace config now reserves an optional `reviews.contradictions` section:

- `enabled`
- `provider`
- `model`
- `max_candidate_pages`
- `review_task_priority`

Current runtime behavior:

- contradiction review is scoped to existing source-summary pages during ingest
- OpenAI-backed contradiction review runs only when `OPENAI_API_KEY` is configured
- missing provider credentials degrade cleanly to a run warning instead of failing ingest

## Current storage decision

The schemas are implemented as Python-native models first, with JSON sidecars for records that need
to exist before markdown renderers and richer file contracts are ready. That keeps the initial
implementation small while preserving deterministic validation and future compatibility with YAML
frontmatter or richer sidecar layouts.

The next storage-oriented schema change should preserve that philosophy: keep manifests
filesystem-native and explicit, but make source resolution policy first-class instead of baking a
copy-under-`raw/sources/` assumption into a single `path` field.
