# Source Resolution Refactor Plan

## 1. Purpose

This document defines the planned refactor from Splendor's current copy-everything source model to
a source-resolution model that separates:

- the canonical source reference
- the storage policy applied to that source
- any optional materialized artifact created under `raw/sources/`

The immediate driver is in-repo source handling. When a markdown file, code file, or config file
already lives inside the tracked repository, Splendor should not duplicate it into `raw/sources/`
by default. Instead, Splendor should register the repo file as the canonical source, verify it by
checksum during ingest, and only materialize a snapshot when the project explicitly opts in.

## 2. Problem Statement

The current MVP source contract assumes that registration means "copy the file into
`raw/sources/<source_id>/...` and treat that stored copy as the source of bytes for ingest." That
has several problems for in-repo text sources:

- it duplicates repo-native files that are already versioned by git
- it creates noisy pull requests and bloated repository trees
- it overfits the model to one storage strategy instead of a general source-resolution contract
- it makes later support for pointers, symlinks, remote sources, and imported artifacts harder than
  it needs to be

The refactor should preserve provenance and determinism while making repo-native behavior the
default for repo-native sources.

## 3. Design Goals

1. Make in-repo file registration repo-native by default.
2. Preserve durable materialization for external local files and imported sources.
3. Introduce one source-resolution layer used by registration, ingest, and later richer source
   handlers.
4. Keep the migration path incremental and compatibility-friendly.
5. Reduce content duplication in `wiki/sources/` for sources that are already directly readable from
   the repository.

## 4. Non-Goals

- Implement PDF, OCR, or remote fetch workflows in this change.
- Replace the filesystem with a database-backed source registry.
- Remove `raw/sources/` entirely.
- Require companion-repo mode.

## 5. Proposed Source Model

### 5.1 Conceptual model

Each source has:

- a **canonical source reference**
- a **source reference kind**
- a **storage mode**
- an optional **storage path**
- a registered **checksum**

### 5.2 Canonical source reference

This is the thing the user intends Splendor to track.

Examples:

- `docs/spec.md`
- `src/splendor/commands/ingest.py`
- `/Users/alice/Desktop/reference-notes.md`
- `https://example.com/paper`

### 5.3 Storage mode

This describes how Splendor makes the source available for ingest.

Proposed initial values:

- `none`
  - No materialized artifact is created.
  - Used by default for in-repo files.
- `copy`
  - Materialize a copy under `raw/sources/`.
  - Default for external local files and imported sources.
- `symlink`
  - Optional project-selected mode for repos that want a `raw/sources/` directory without byte
    duplication.
- `pointer`
  - Materialize a small metadata artifact under `raw/sources/` that points at the canonical source.
  - Cross-platform alternative to `symlink`.

### 5.4 Source-resolution rule

Every command that needs source bytes should resolve them through one shared abstraction:

`resolve_source_content(record) -> ResolvedSource`

The resolved object should answer:

- where bytes will be read from
- whether the content came from the workspace or a materialized artifact
- what validation was applied before use

## 6. Proposed Schema Changes

### 6.1 `SourceRecord`

Current fields to keep:

- `schema_version`
- `kind`
- `source_id`
- `title`
- `source_type`
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

New fields to add:

- `source_ref`
- `source_ref_kind`
- `storage_mode`
- `storage_path`
- `materialized_at`
- `source_commit`

Compatibility plan:

- keep reading old manifests that only have `path`
- treat old `path` as a legacy storage path
- keep `path` as a compatibility field while new registrations also write the explicit
  source-resolution fields
- defer any manifest rewrite or schema-version bump to a later release

### 6.2 Proposed field definitions

### `source_ref`

Canonical source identifier.

Examples:

- `docs/spec.md`
- `/Users/alice/Desktop/notes.md`
- `https://example.com/spec`

### `source_ref_kind`

Initial enum:

- `workspace_path`
- `external_path`
- `url`
- `imported`
- `stored_artifact`

### `storage_mode`

Initial enum:

- `none`
- `copy`
- `symlink`
- `pointer`

### `storage_path`

Optional repo-relative path, usually under `raw/sources/`, used when a source is materialized.

### `materialized_at`

Timestamp capturing when the storage artifact was created or refreshed.

### `source_commit`

Optional git commit SHA captured for clean tracked workspace files when stronger repo-native
provenance is desired.

## 7. Proposed Config Changes

Add a source-policy section to `splendor.yaml`.

Example:

```yaml
schema_version: "1"
project_name: "Splendor workspace"

layout:
  raw_sources_dir: "raw/sources"
  wiki_dir: "wiki"
  state_dir: "state"

sources:
  in_repo_storage_mode: none
  external_storage_mode: copy
  imported_storage_mode: copy
  capture_source_commit: true
  summarize_in_repo_extracts_as: excerpt
  summarize_external_extracts_as: full
```

### 7.1 Config semantics

- `in_repo_storage_mode`
  - Default policy for repo-relative files.
  - Initial supported values: `none`, `copy`, `symlink`, `pointer`.
- `external_storage_mode`
  - Default policy for local files outside the workspace root.
- `imported_storage_mode`
  - Default policy for future fetched or imported sources.
- `capture_source_commit`
  - If true, record the current git commit for clean tracked workspace files.
- `summarize_in_repo_extracts_as`
  - Initial values: `none`, `excerpt`, `full`.
- `summarize_external_extracts_as`
  - Initial values: `excerpt`, `full`.

## 8. Proposed CLI Changes

### 8.1 `splendor add-source`

Current:

```bash
splendor add-source <path>
```

Proposed additions:

```bash
splendor add-source <path> [--storage-mode none|copy|symlink|pointer]
splendor add-source <path> [--capture-source-commit/--no-capture-source-commit]
```

Behavior:

- if `<path>` is inside the workspace and no override is provided:
  - use `storage_mode=none`
- if `<path>` is outside the workspace and no override is provided:
  - use the configured external default, initially `copy`
- if the requested mode conflicts with source kind or platform constraints:
  - fail with a clear validation error

### 8.2 `splendor ingest`

Current:

```bash
splendor ingest <source-id>
splendor ingest --pending
```

Proposed internal behavior changes:

- ingest must no longer assume `raw/sources/` contains the source bytes
- ingest must call the shared resolver and record the resolved input in run metadata
- ingest should warn clearly if a workspace-backed source no longer matches the registered checksum

### 8.3 Optional future command

Not required in Phase 1, but likely useful later:

```bash
splendor materialize-source <source-id>
```

This would allow an existing workspace-backed source to be snapshotted on demand.

## 9. Source Summary Page Policy

The current source-summary pages include a large `## Extract` block. That is acceptable for external
or transformed sources, but it is too noisy for in-repo text files.

Proposed default policy:

- for in-repo text sources:
  - include metadata
  - include provenance
  - include the canonical source path
  - include a short excerpt or no excerpt, based on config
- for external or transformed sources:
  - include a fuller extract when it materially helps with local readability and provenance

This keeps `wiki/sources/` useful without turning it into a second docs tree.

## 10. Detailed Implementation Plan

The work should proceed in two phases. Each phase may span multiple PRs.

### 10.1 Phase 1 — Introduce the source-resolution model

### Goal

Make the core source manifest and ingest path understand canonical references and storage modes.

### Phase 1 outcomes

- new source schema fields exist
- in-repo files default to `storage_mode=none`
- external files continue to default to `copy`
- ingest reads through a resolver abstraction
- older manifests still work

### Recommended PR breakdown

Planning note:

- the rollout steps below use `SR-n` labels (`Source Resolution`) to distinguish plan items from GitHub PR numbers

#### SR-1 — Docs and contract alignment

Scope:

- update product spec
- update roadmap
- update schema contracts
- add this implementation plan

Exit criteria:

- docs agree on the target architecture before code changes begin

#### SR-2 — Schema and config scaffolding

Scope:

- add new `SourceRecord` fields
- add new config surface under `sources`
- keep compatibility with old manifests
- add tests for schema parsing and defaults

Exit criteria:

- manifests can express source reference and storage policy
- config defaults can encode workspace-vs-external behavior

#### SR-3 — Source resolver abstraction

Scope:

- introduce a shared resolver module
- resolve source bytes for:
  - workspace-backed sources
  - copied sources
  - legacy manifests
- update ingest to use the resolver

Exit criteria:

- ingest no longer assumes `raw/sources/` is always the place to read bytes from

#### SR-4 — `add-source` default behavior switch

Scope:

- change in-repo registration default to `storage_mode=none`
- preserve `copy` default for external local files
- add CLI override flag for `--storage-mode`
- add optional capture of git commit for clean tracked workspace files

Exit criteria:

- in-repo files stop being copied by default
- explicit overrides still work

#### SR-5 — Migration and polish

Scope:

- compatibility helpers for legacy manifests
- upgrade notes
- more fixture coverage
- run metadata improvements for resolved input refs

Exit criteria:

- older workspaces continue to ingest cleanly
- the new behavior is documented and tested

### 10.2 Phase 2 — Reduce rendered duplication and add optional materialization paths

### Goal

Make the wiki output and storage options match the new source model ergonomically.

### Phase 2 outcomes

- source-summary pages stop reproducing full in-repo docs by default
- optional pointer and symlink materialization paths exist
- projects can opt into stronger snapshot behavior where they need it

### Recommended PR breakdown

Planning note:

- phase 2 continues the same `SR-n` sequence rather than restarting with GitHub PR numbers

#### SR-6 — Source-summary rendering policy

Scope:

- activate config-driven extract strategy during ingest
- default in-repo summaries to short excerpts
- preserve fuller extracts for external or transformed sources
- update tests for deterministic page rendering

Exit criteria:

- `wiki/sources/` becomes materially less noisy for in-repo docs and code

#### SR-7 — Pointer storage mode

Scope:

- define pointer artifact format
- add `storage_mode=pointer`
- teach resolver to follow pointer artifacts

Exit criteria:

- projects have a cross-platform materialization alternative that does not duplicate bytes

#### SR-8 — Optional symlink mode

Scope:

- add guarded `storage_mode=symlink`
- validate platform constraints
- document operational caveats

Exit criteria:

- projects that prefer filesystem-level mirroring can opt in knowingly

#### SR-9 — Materialization workflow polish

Scope:

- optional `materialize-source` command or equivalent workflow
- better reporting of canonical source vs storage artifact
- health/lint checks for invalid storage policies or broken pointers/symlinks

Exit criteria:

- source materialization is operationally understandable and repairable

## 11. Risks and Tradeoffs

### Risk: weaker immutability for workspace-backed sources

Mitigation:

- enforce checksum verification during ingest
- optionally capture `source_commit`
- provide explicit copy/pointer modes for projects that want stronger materialization

### Risk: migration complexity

Mitigation:

- keep read compatibility for legacy manifests
- split schema, resolver, and CLI behavior changes across multiple PRs

### Risk: design drift between docs and implementation

Mitigation:

- land the documentation PR first
- treat this file as the implementation sequence until Phase 2 is complete

## 12. Recommended Default Decisions

These should be treated as the proposed baseline unless implementation uncovers a blocking issue:

- default in-repo storage mode: `none`
- default external local storage mode: `copy`
- source-summary rendering for in-repo text files: `excerpt`
- source-summary rendering for external or transformed text: `full`
- capture git commit for clean tracked workspace files: `true`

## 13. Merge and Follow-up

After this design PR is merged, implementation should proceed as the PR series described above. The
first code PR should focus on schema and config scaffolding, not on UI polish or richer source
types.
