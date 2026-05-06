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
- `logical_id`
- `aliases`
- `supersedes`
- `superseded_by`
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
- `logical_id`
  - Stable logical source identity for workspace-backed sources.
  - New workspace-backed registrations use `source:<workspace-path>`, for example
    `source:docs/spec.md`.
  - Content-addressed `source_id` values remain the canonical manifest filenames, queue payload
    targets, run provenance, and generated source-summary page identifiers.
- `aliases`
  - Stable lookup aliases for the logical source identity.
  - Workspace-backed registrations include the repo-relative path alias, and lookup/freshness JSON
    also exposes the effective logical ID as an alias for agent handoff.
  - External and legacy manifests may leave this empty.
- `supersedes`
  - Source version IDs this record supersedes.
  - Refresh writes the previous active content-addressed `src-...` ID here when a changed
    workspace-backed source creates a new source version.
- `superseded_by`
  - Source version ID that replaced this record for the same logical source.
  - Health treats superseded workspace-backed records as historical version records instead of
    active current-byte targets, so old run/page provenance remains valid after refresh.
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
- `splendor source list` and `splendor source lookup [query]` provide a readable title/path/logical
  ID to `source_id` mapping. They are lookup surfaces only and do not rename canonical source IDs or
  generated `wiki/sources/src-...md` pages.
- Mutating source commands resolve source selectors strictly. Direct ingest accepts exact source
  IDs, exact logical IDs, exact path aliases/source refs, or exact unambiguous titles; substring
  matches remain limited to read-only lookup surfaces.
- `splendor source refresh <source-id|logical-id|title|path>` resolves the tracked workspace or
  external path, compares current bytes to the manifest checksum, registers changed content as a
  new canonical source version, preserves `source_commit_capture` intent, links the old and new
  versions with `supersedes` / `superseded_by`, and queues ingest through the same queue handoff
  used by `add-source`.
- `splendor source update-path <source-id|logical-id|title|path> <new-path>` repairs the manifest
  for an active curated workspace-backed source after an intentional file move. The first
  implementation supports `storage_mode: none` and `storage_mode: copy` workspace sources. By
  default it requires the old workspace path to be missing; `--force` allows explicit reparenting
  while the old path still exists. It validates that the target is a supported file inside the
  workspace, rejects paths already curated by another active source, preserves the stable
  `logical_id` and original-path alias, adds the new path alias, updates `source_ref`, and updates
  the compatibility `path` field for `storage_mode: none`, then validates and rewrites the
  schema-bound manifest. Same-byte repairs
  mark previously ingested source records as needing ingest and queue the existing source ID so
  generated source-summary provenance can refresh. Changed-byte repairs return `status: partial`,
  do not queue ingest, and point operators to `splendor source refresh <new-path>`. Human and JSON
  output report source ID, old path, new path, status, manifest/current checksums, checksum match
  status, manifest path, queue path when present, and next commands. It does not discover or
  register uncurated files, rewrite historical run records, or mutate maintained synthesis pages.
- `splendor source forget <source-id|logical-id|title|path>` and
  `splendor source forget --matching <workspace-relative-glob>` provide preview-first registry
  cleanup for polluted source manifests. The command requires exactly one selection mode, previews
  by default, and requires `--apply` before deletion. Single-source selectors use the same strict
  exact source resolution as mutating source commands. `--matching` compares the glob against
  workspace source refs, original paths, aliases, logical IDs, and compatibility paths in
  deterministic order. Apply removes selected manifests plus source-owned generated source-summary
  pages, ingest queue records, source-owned ingest run records, safe derived artifacts, and
  materialized artifacts under the source-owned raw artifact directory. Maintained wiki/planning
  references, malformed generated pages, mixed run records, and unsafe artifacts are reported as
  residual or skipped references rather than rewritten.
- `splendor queue clean --orphaned|--superseded|--completed` provides preview-first closure for
  stale ingest queue records. The command requires at least one selector, previews by default, and
  requires `--apply` before deleting queue JSON. It selects only valid source-owned `ingest_source`
  records that are not actively leased: `--orphaned` for missing source-manifest payloads,
  `--superseded` for queue records whose payload source has `superseded_by`, and `--completed` for
  `done` queue records. JSON output includes `mutation.mode`, `mutation.mutates`,
  `mutation.planned`, and `mutation.written`; skipped records report invalid payloads, unsupported
  job types, active leases, queue filename/job ID mismatches, and source/job mismatches without
  deleting them.
- `splendor source reconcile <source-id|logical-id|title|path>` previews duplicate active source
  version repair for one canonical source-ref group. Without `--current`, an exact source ID keeps
  that source active; otherwise the latest active version by `(added_at, source_id)` is selected.
  `--current <selector>` must resolve to exactly one active source in the same canonical group.
  `--apply` writes only affected source manifests, setting `superseded_by` on older active
  versions and appending those source IDs plus same-canonical one-way links to the current record's
  `supersedes` list. Ambiguous, unknown, superseded-current, and cross-canonical selections fail
  without manifest writes.
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
- `splendor workspace refresh --changed` is the safe workspace-level mutating path over curated
  workspace-backed source manifests. It uses `source freshness` to select changed active manifests,
  reports missing or unsupported active curated workspace sources as skipped unresolved diagnostics,
  refreshes each changed source through the supersession-aware source refresh path, records
  per-source refresh failures instead of aborting the whole command, and can ingest only the queue
  records created or reused for successful refreshed sources with `--ingest`. The command exits
  non-zero when unresolved skipped sources, failed source refreshes, or targeted ingest failures
  remain, while preserving successful refresh and ingest work.
- `splendor workspace refresh --rebuild-index` rebuilds `wiki/index.md` as standalone maintenance
  or after any requested changed-source refresh, targeted ingest, pruning, or topic-ref migration.
  `--changed --ingest` drains only refreshed-source queue records, not unrelated pending ingest
  jobs. JSON output reports both initial and final freshness counts plus skipped-source,
  failed-refresh, targeted-ingest, index, pruning, and topic-ref migration diagnostics.
  `--prune-superseded` deletes superseded generated source-summary pages after a current successor
  summary exists, removes the pruned
  generated-page link from the superseded source manifest, and preserves historical source
  manifests and run records. Health treats run page refs for those exact pruned superseded
  workspace summaries as valid historical provenance without exempting unrelated broken run refs.
  Prune JSON reports skipped unsafe candidates with reasons. `--update-topic-refs` rewrites
  maintained wiki page `source_refs` and generated source-reference list bullets from superseded
  source IDs to the active content-addressed source version, leaving prose and code-fence mentions
  untouched. The command does not perform broad repo discovery, register uncurated files, or run
  mutating synthesis compile/update workflows.

- `splendor ingest --changed` is the narrow stale-source ingestion path for checksum-drifted
  curated workspace-backed sources. It scans source freshness, reports missing active curated
  workspace sources as unresolved diagnostics, refreshes each changed source through the existing
  supersession-aware source refresh path, and runs only the refreshed sources' queue records. It
  reports a clean no-op when no curated workspace-backed source bytes changed. `--json` emits
  initial and final freshness counts, missing-source diagnostics, refreshed source IDs, targeted
  queue outcomes, and summary counts.
- `splendor ingest --pending --json` emits the same pending queue drain contract as human output in
  structured form: queue total, processed/succeeded/failed/skipped summary counts, per-item source
  IDs, workspace-relative queue paths, outcomes, messages, and deterministic next actions.
  As of the v0.4 external review, this remains a legacy direct-drain command: it mutates queue,
  source-summary, run, and index/log state when work is available. The planned durability contract
  is to give this flow the same agent-safe preview/apply clarity as newer cleanup commands, or to
  expose an explicitly named destructive drain form so inspection and mutation cannot be confused.
- `splendor wiki compile <source-id|title|path>` remains non-mutating unless a maintained target
  page is selected and `--apply --proposal-hash <hash>` is supplied. Without `--page`, it reports
  the review-gated contract plus ranked maintained-page suggestions and ready-to-run
  `splendor wiki compile <source-id> --page <page>` preview commands. JSON suggestions include
  both the rendered `compile_preview_command` string for human handoff and `compile_preview_args`
  argv tokens for tools that should not parse shell text. `splendor wiki suggest
  <source-id|title|path>` emits the same preview command and args in human and JSON output.
  `--page <maintained-page>` proposes a deterministic update from the generated source-summary
  page into one maintained topic, concept, entity, architecture, or glossary page. Proposed output
  includes a unified diff, target/source-summary SHA-256 hashes, and a proposal hash derived from
  those inputs plus the proposed page hash. Proposed and applied updates add the source ID to
  frontmatter `source_refs`, add provenance links with `supports` and `generated-from` roles,
  append a managed `Compiled Source Evidence` section to the markdown body, and validate the
  resulting `KnowledgePageFrontmatter` before reporting or writing. Generated source-summary pages
  are not valid compile targets.
- Agent-safe preview/apply outputs use an additive `mutation` object where mutating behavior is
  already part of the command contract. `mutation.mode` is `preview` or `apply`, `mutation.mutates`
  is true only when the invocation wrote or removed workspace state, `mutation.planned` lists
  deterministic planned write/delete records for preview mode, and `mutation.written` lists
  deterministic write/delete records for apply or direct-write mode. Records include `action`,
  `path`, `kind`, and `source_id` when source-scoped.
- Post-v0.4 contract debt: legacy mutating commands must not rely on agents remembering bespoke
  safety semantics. `ingest --pending`, `source refresh`, `source update-path`, and
  `workspace refresh` should either become preview-first with explicit `--apply`, or expose
  deterministic mutation objects and human output that make direct writes unmistakable before the
  command is run from handoff guidance.
- `splendor pr-summary --since main` is a read-only PR handoff view over local git diff/status and
  existing report files. It diffs from the merge base between `HEAD` and the base ref, respects
  configured workspace layout directories, and groups curated source manifests, generated
  source-summary pages, maintained wiki/topic pages, queue/run/report/derived generated-state
  churn, latest local lint/health report status when available, and reviewer notes. Malformed
  changed source manifests are reported as invalid curated-source changes instead of aborting the
  whole summary. Human output includes a compact committed review section before detailed path
  groups. `--json` emits the same structure for agents, including `compact_review` with
  `review_first`, `usually_mechanical`, and `attention` groups so reviewers can distinguish
  generated knowledge changes from mechanical queue/run/report/query/derived churn. Compact groups
  keep `paths` for quick scanning plus `path_actions` and `action_counts` for add/change/delete/
  rename review without falling back to the detailed groups. The command does not create
  manifests, queue jobs, wiki pages, run records, reports, or GitHub state.
- `splendor brief --agent-context [--since <ref>] [--no-git] [goal]` and
  `splendor suggest-next [--since <ref>] [--no-git] [goal]` are read-only handoff views over
  existing deterministic state plus runtime-only git/GitHub signals. They do not create planning
  records, queue jobs, manifests, wiki pages, run records, reports, or GitHub state. Human output
  is path-first where possible; `--json` emits ranked action objects with category, priority,
  title, reason, command, path, optional URL, source ID/source ref, planning/page record IDs, and a
  deterministic `relevance_score` when available. Runtime authority entries also expose `origin`,
  `curation_state`, and `curation_commands`; provisional uncurated authority is repeated under
  `provisional_context` so agents can use it without confusing it for configured or curated source
  authority. Maintenance context also exposes runtime-only command guidance and explanatory notes
  so review-needed wiki state, missing synthesis, queue drift, source freshness, and generated
  contradiction-review tasks stay discoverable without becoming default human planning records.
- Suggested actions are derived from local git commits, best-effort read-only GitHub issue/PR
  context through `gh` when available, source freshness, queue operator state, invalid/stale/
  contested/review-needed wiki pages, ingested sources missing maintained synthesis follow-up,
  active planning records, recent lint/health reports, and optional goal query matches. Non-
  maintenance goals rank work context before Splendor maintenance. Goal relevance is scored
  deterministically from weighted title/path/record/scope matches, supporting refs, snippets,
  git/GitHub text, and review/authority lifecycle signals before category caps are applied.
- Planned handoff inference contract: when runtime git/GitHub state indicates that a referenced
  PR, issue thread, or roadmap slice is merged or complete, and an ordered roadmap or current-state
  authority names a successor slice, handoff should demote the completed work to supporting context
  and rank the successor as the next work item. Stale `.agent-plan.md` or roadmap "current" text is
  still useful evidence, but it should be reconciled against merge state and explicit roadmap order
  before becoming the top suggested action.
- Work-thread surfacing should preserve breadth. The JSON and human handoff can lead with the best
  open issue or PR, but should also include a bounded set of related open parent/sibling threads
  when goal terms, labels, issue references, or recent merged PR bodies connect them.
- Files-to-read ranking may use high-authority path and symbol references as deterministic hints.
  Paths and tests named by authority docs should rank above broad historical docs when they are
  directly tied to the goal.
- Text-bearing PDF sources are routed through source-type dispatch during ingest. The source
  manifest keeps the same `source_ref`, `source_ref_kind`, and `storage_mode` contract as
  text-native sources, while extracted text artifacts are recorded in `derived_artifacts`.
- Image sources and image-only PDFs use the same source registration and resolver contract. OCR is
  optional and explicitly configured; successful OCR-derived text is recorded in
  `derived_artifacts` without changing the canonical source identity. Sidecar OCR inputs are
  tracked through metadata artifacts so no-op ingest can detect sidecar checksum drift.

### Source identity disposition

Issue #94's stable source-identity concern is handled in schema version `1` by layering stable
logical selectors and lifecycle links over immutable content-addressed records, rather than by
renaming canonical IDs:

- Canonical source manifests, queue payloads, generated source-summary pages, and run provenance
  continue to use content-addressed `src-...` IDs for compatibility.
- Workspace-backed curated sources persist or derive `source:<workspace-path>` logical IDs and path
  aliases so operators can select the logical source across ordinary content edits. After an
  explicit path repair, the original logical ID remains a stable selector and the new path is added
  as a path alias.
- Changed content is represented as a new canonical source version linked to the previous version
  with `supersedes` / `superseded_by`; historical manifests and run records remain valid.
- Checksum/freshness state stays on each source version and in explicit freshness reports; it is not
  the logical identity.
- Intentional file moves are handled by `splendor source update-path`, which updates the active
  source ref and compatibility path fields while preserving the stable logical ID and old path
  alias, without discovering uncurated files or rewriting historical run records.
- Maintained topic/source refs can be migrated from superseded source IDs to active versions with
  `workspace refresh --update-topic-refs` after refreshed successor summaries exist.

This disposition keeps schema version `1` stable. Future identity work should name a specific
remaining gap, such as non-workspace source lifecycle semantics, rather than replacing the canonical
`src-...` compatibility contract.

Legacy SHA/content-addressed manifests remain compatible. If a workspace-backed record has
`source_ref_kind: workspace_path` but lacks `logical_id` or aliases, lookup/freshness derives the
effective logical ID from the recorded workspace path and re-registration or path repair backfills
the persisted selector fields. Older copied/stored-artifact records that do not carry
workspace-backed source refs keep their canonical `src-...` identity until an operator explicitly
re-registers or otherwise curates them as workspace-backed sources.

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
- source IDs remain content-addressed canonical IDs; stable logical source aliases and
  `supersedes`/`superseded_by` lifecycle fields now describe workspace-backed refresh history
  without changing schema version `1`
- explicit pruning of superseded source-summary pages and maintained-page source-ref migration are
  workspace maintenance operations over existing schema version `1` fields, not a manifest schema
  rewrite
- safe workspace refresh composes existing source, queue, ingest, wiki-index, and wiki-frontmatter
  records without changing schema version `1`
- PR-summary output is derived from existing schema-version-1 files and local git state; it is not a
  persisted schema and does not require a schema-version bump

## Knowledge page frontmatter

Minimal frontmatter contract for wiki pages:

- `schema_version`
- `kind`
- `title`
- `page_id`
- `status`
- `review_state`
- `authority_role`
- `authority_freshness`
- `authority_lifecycle`
- `authority_scope`
- `issue_refs`
- `pr_refs`
- `supersedes`
- `superseded_by`
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
- maintained wiki pages may opt into agent authority ranking with `authority_role`,
  `authority_freshness`, `authority_lifecycle`, `authority_scope`, issue/PR refs, and
  supersession links; generated `source-summary` pages are ignored by maintained authority ranking
  even if those fields are present
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

## Briefing authority metadata

`splendor.yaml` may include a `briefing.authority_documents` list for maintained planning,
roadmap, schema, automation, release, and design documents that are not wiki pages. Each entry is
schema-version-1-compatible config, not generated state:

- `path`: normalized repo-relative document path; absolute paths, parent traversal, empty paths,
  and backslash separators are rejected
- `role`: one of `current-authority`, `roadmap`, `historical-review`, `proposal`, `reference`, or
  `generated-summary`
- `freshness`: one of `current`, `watch`, `stale`, or `historical`
- `authority_lifecycle`: optional lifecycle state; one of `current`, `reviewed`, `pr-linked`,
  `historical`, `superseded`, or `archived`
- `title`: optional display title
- `purpose`: optional handoff reason
- `applies_to`: optional task/topic terms used during goal ranking
- `issue_refs`: optional issue identifiers such as `#116`
- `pr_refs`: optional PR identifiers such as `#132`
- `supersedes`: optional authority docs or decision IDs replaced by this entry
- `superseded_by`: optional authority doc or decision ID that replaced this entry

`splendor brief --agent-context [goal]` and `splendor suggest-next [goal]` use this metadata as a
read-only ranking signal. Omitted lifecycle metadata remains schema-version-1-compatible:
configured docs default to current unless role/freshness marks them historical or an explicit
`superseded_by` replacement exists, and wiki authority lifecycle is derived from review state,
freshness, review timestamp, and supersession fields. Stale freshness remains separate from
supersession. Missing configured files are excluded from the ranked authority list, reported as
authority warnings in the brief, and surfaced by `splendor lint` as
`missing-authority-document`.

Accepted and superseded decision records can also participate in goal-relevant authority handoff.
Accepted decisions default to reviewed authority, while superseded decisions default to superseded
historical context. Optional decision `authority_lifecycle`, `issue_refs`, `pr_refs`,
`superseded_by`, and existing `supersedes` fields are included in authority JSON output when
present. `splendor decision create` can write those optional fields with `--authority-lifecycle`,
`--issue-ref`, `--pr-ref`, and `--superseded-by`.

Task records now also reserve:

- `record_origin`
- `generated_kind`
- `review_task_state`
- `page_refs`
- `run_refs`

`record_origin` defaults to `human`. Ingest-created contradiction-review tasks use
`record_origin: generated`, `generated_kind: contradiction-review`, and
`review_task_state: active`. Operators can move those generated review tasks to `resolved` or
`muted`; resolved tasks also use `status: done`. Those fields let default planning handoff
prioritize human-authored planning records while preserving explicit links back to the affected
wiki pages and the ingest run that surfaced the conflict.

Review-needed wiki pages and sources missing maintained synthesis are not represented as ordinary
task records by default. Operators review them through `splendor wiki status`, `splendor wiki
suggest <source-id>`, and the maintenance context in `brief --agent-context` / `suggest-next`.

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
- Ingest run records capture `started_at` with sub-second precision before source
  resolution/dispatch work begins, and set `finished_at` only when the run reaches terminal
  success or failure. Historical run records are not rewritten.

Current persisted locations:

- `state/queue/<job_id>.json`
- `state/runs/<run_id>.json`

Queue status values are `pending`, `leased`, `done`, `failed`, and `dead_letter`. Failed records may
carry `next_attempt_at` to defer the next automatic `splendor ingest --pending` retry. Dead-letter
records preserve `last_error` and require an explicit `splendor queue retry <job-id>` or
`splendor repair ingest <source-id>` action. Queue inspection also reports additive
`cleanup_state` values so `orphaned`, `superseded`, `completed`, `active_leased`,
`invalid_payload`, and `not_cleanup_candidate` records can be distinguished without parsing
payload paths by hand.

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

## Maintenance report records

`splendor lint` and `splendor health` write timestamped JSON and Markdown reports under
`reports/<command>/`. `MaintenanceIssue` carries:

- `code`
- `message`
- `path`
- `record_id`
- `check_name`
- `remediation_hint`

`remediation_hint` is optional and deterministic. Health uses it only when the current diagnostic
has a known safe operator action: missing active workspace source paths point to `splendor source
update-path ... <new-path>` and `splendor source freshness`; checksum drift points to
`splendor source refresh ...`, `splendor ingest --pending`, or `splendor ingest --changed`;
failed/dead-letter queue diagnostics and expired leases point to queue retry or ingest repair
commands. Unknown source provenance references stay diagnostic-only and explicitly avoid a broad
rewrite command. Run `source_ids` and provenance source links are resolved against parsed source
manifest records separately from source content/storage health, so checksum drift or missing live
workspace files do not make existing manifest IDs appear unknown.

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
  `splendorignore`, `scan_control`, `include_patterns`, `exclude_patterns`, or `class_filter`;
  pruned ignored directories are reported with trailing slash paths when they represent populated
  non-layout trees
- mutating registration requires `--apply` plus `--class ...` or `--all`
- large apply runs require `--allow-large-apply` after preview review
- scan honors `sources.include_patterns`, `sources.exclude_patterns`, and
  `sources.repo_scan_default_classes` from `splendor.yaml`, plus optional root `.splendorignore`
  project-specific ignore patterns
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

## Schema-version-1 readiness notes

- The current schema version remains `1`; M13-P3.1 does not introduce a migration or rewrite
  existing manifests.
- The release-ready core is file-based, deterministic, and compatible with legacy `path`-only
  source manifests.
- Source freshness, suggest-next, and agent briefing use existing records as read-only signals.
- Stable logical source identities, supersession-aware history, superseded summary pruning,
  maintained-page source-ref migration, and PR-summary handoff output are all
  schema-version-1-compatible layers above the content-addressed `source_id` compatibility
  contract.
- Lint validates present workspace-backed logical identity fields: `logical_id` must match
  `source:<source_ref>`, persisted aliases must stay scoped to the canonical workspace path, and
  exact identities must not point at conflicting canonical source refs.
- The `v0.2.0` and `v0.3.0` evaluation releases kept schema version `1`; the final v1-style handoff
  in `docs/releases/v1_release_handoff.md` treats schema version `1`, legacy manifest compatibility,
  and deferred source-lifecycle fields as release checklist items rather than implicit assumptions.
- The v0.4 handoff direction should remain schema-version-1-compatible: git context, inferred
  authority labels, provisional uncurated-doc context, maintenance-section ranking, and
  maintenance command guidance are runtime briefing signals unless a later PR explicitly defines
  persisted fields.

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
