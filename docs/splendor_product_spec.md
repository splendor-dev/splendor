# Splendor Product Specification

## 1. Overview

**Splendor** is a local-first, git-native, schema-driven agent context system for
code-and-research repositories. It maintains curated project knowledge, provenance, planning
objects, freshness signals, and reviewable synthesis in markdown and structured sidecars so humans
and agents can decide what is trustworthy, stale, contested, and actionable.

The product is inspired by the LLM Wiki pattern: a persistent wiki that is continuously updated as new source material arrives, instead of re-deriving knowledge from raw documents at query time. In Splendor, that pattern is adapted specifically for software projects that require substantial research, domain knowledge, technical decision tracking, and project planning. The uploaded concept note emphasizes the persistent wiki as the central compounding artifact, with raw sources remaining immutable and the LLM maintaining the synthesized layer. fileciteturn0file0L6-L18 fileciteturn0file0L35-L43

Issue #70 clarified that this wiki layer must not become a noisy mirror of files agents can already
read directly. Splendor should distinguish discovery from curation, keep source manifests
intentional, and generate synthesis when it adds cross-source value, freshness context,
contradiction handling, or handoff value.

## 2. Product Goals

### Core goals

1. **Maintain curated project context in git**
   - The knowledge workspace lives either inside the code repository or in a companion repository.
   - The durable state is markdown and schema-bound sidecars optimized for GitHub readability and
     reviewability.

2. **Support incremental source ingestion**
   - Curated sources are added to the repository and processed into structured knowledge updates.
   - Existing wiki pages are updated rather than recreated from scratch.

3. **Treat provenance as a first-class concern**
   - Wiki claims and summaries should be traceable to source artifacts and ingestion runs.
   - The system should preserve enough structure to support trust, debugging, and re-ingestion.

4. **Support code-aware project understanding**
   - Splendor should understand the repository’s code, structure, documentation, plans, and adjacent research materials as a unified project knowledge space.

5. **Support project management inside the wiki**
   - Milestones, tasks, decisions, and open questions should be represented as structured, queryable objects rendered as markdown.

6. **Be usable both by humans and coding/research agents**
   - The CLI is the primary operational interface.
   - A local web UI is optional, useful for browsing and interaction, but not required for agent workflows.

7. **Be GitHub-powered but not GitHub-dependent**
   - Local operation must be possible without GitHub.
   - Strong optional GitHub-native features are welcome and encouraged.

### Non-goals for early versions

1. A hosted SaaS platform.
2. A replacement for full project hosting platforms or enterprise knowledge systems.
3. A fully autonomous research agent that operates without supervision.
4. A heavy distributed job orchestration platform.
5. A mandatory embeddings/vector database stack.

## 3. Product Philosophy

Splendor is built around a few principles:

- **Local-first authoring and ingestion**
- **Git-native collaboration and review**
- **Persistent knowledge over stateless retrieval**
- **Curated source intent over broad file mirroring**
- **Structured provenance over opaque synthesis**
- **Deterministic maintenance where rules suffice**
- **LLMs for semantic work, not for every operation**
- **Optional GitHub-native acceleration, not hard platform lock-in**

## 4. Core Conceptual Model

Splendor has seven conceptual layers.

### 4.1 Source Candidates and Curated Sources

Splendor distinguishes files it discovers from sources the user intentionally curates.

**Source candidates** are files or external references found by discovery workflows. Candidate
reports may classify and rank them, but candidates are not part of the durable source registry until
the user accepts them.

**Curated sources** are immutable source artifacts that represent the project’s evidence base and
are recorded in the configured source-record registry. The default registry path is
`state/manifests/sources/`; non-default layouts use `layout.source_records_dir` in
`splendor.yaml`.

Examples:
- markdown notes
- PDFs
- images
- audio transcripts
- web-clipped articles
- architecture docs
- issues exported as markdown
- design docs
- code files or code snapshots

The source layer is append-oriented. Sources are not mutated by LLM workflows. Discovery must not
create large manifest or wiki churn unless the user explicitly applies a curated selection.

Splendor now defaults to workspace-backed registration for in-repo files and materialized copies
for external local files. Materialization under `raw/sources/` remains useful for external and
unstable inputs, but it is too blunt for repositories whose markdown, code, and configuration files
already live inside git. The source model therefore distinguishes between:

- the **canonical source reference** the user means Splendor to track
- the **storage policy** Splendor applies to make that source available to the pipeline
- any optional **materialized snapshot or pointer artifact** Splendor creates for provenance,
  portability, or repairability

### 4.2 Discovery Reports

Machine-readable reports produced by non-mutating discovery workflows.

Examples:
- repo scan candidate reports
- include/exclude match summaries
- candidate class counts
- already-curated candidate markers

Discovery reports are not source manifests. They help users and agents decide what to curate.
Planned `splendor repo scan` behavior is:

- default output is a human-readable stdout preview only
- `--json` emits a machine-readable preview to stdout
- persistent report files are written only when the operator passes an explicit report path such as
  `--report PATH`
- preview/report generation must not write source manifests, wiki pages, derived artifacts, queue
  records, or run records
- mutating source registration is allowed only through an explicit apply path

The minimum planned candidate fields are:
- `path`: workspace-root-relative POSIX path or external reference
- `class`: candidate class such as `documentation`, `code`, or `configuration`
- `labels`: deterministic labels assigned during classification
- `status`: `included`, `excluded`, or `already_curated`
- `ignore_reason`: explanation when a candidate is skipped
- `matched_include_patterns` and `matched_exclude_patterns`
- `source_id` and `title` when the candidate is already curated
- `next_command`: exact follow-up command for registration, inspection, or exclusion

### 4.3 Derived Extraction Artifacts

Machine-generated extraction outputs derived from raw sources.

Examples:
- OCR text
- normalized text
- extracted metadata
- captions/descriptions for images
- transcript cleanup
- source summaries
- chunk manifests

These are repairable intermediates, not the wiki itself.

### 4.4 Knowledge Pages

Maintained markdown pages that form the project wiki.

Examples:
- concept pages
- entity pages
- source summary pages
- topic synthesis pages
- glossary pages
- comparison pages
- architecture summaries

These pages are incrementally updated as new sources arrive.

Source-summary pages are ingestion artifacts, not the full compounding synthesis layer. They make a
curated source searchable, reviewable, and traceable to an ingest run. Concept, topic,
comparison, architecture, and overview pages are the maintained synthesis layer where Splendor
turns source evidence into project knowledge. Product workflows should keep that distinction
explicit instead of implying that source-summary generation alone completes wiki maintenance.

Future public concepts should name this distinction directly:
- **Generated source-summary artifact**: a per-source page or sidecar produced by ingest, useful
  when the source is opaque, transformed, external, PDF/OCR-derived, or otherwise hard to inspect
  directly.
- **Maintained synthesis page**: a curated wiki page that compounds evidence across sources,
  decisions, tasks, contradictions, and project history.

### 4.5 Freshness State

Computed state that compares curated source manifests, canonical source paths, generated artifacts,
and wiki pages.

Freshness answers:
- which curated sources changed since their manifest checksum
- which ingests or source summaries are stale
- which synthesis pages need follow-up
- which exact command should move the project state forward

### 4.6 Operational Ledger

Durable operational records that track what happened.

Examples:
- ingestion runs
- queue items
- job results
- retries
- failures
- lint passes
- query filings
- repair attempts

This layer exists to support idempotency, trust, debugging, and recovery.
Ingest run records preserve distinct start and terminal finish timestamps with sub-second
precision for new runs, without rewriting historical ledger entries.

### 4.7 Planning Objects

Structured project-management artifacts rendered as markdown and queryable through the CLI/UI.

Initial object kinds:
- milestone
- task
- decision
- question

## 5. Primary Use Cases

1. **Research-heavy code repository**
   - A codebase plus papers, source evaluations, methodological notes, experiments, and design decisions.

2. **Code repository with a companion knowledge repo**
   - Code remains in one repo; research, plans, and synthesis live in another.

3. **Agent-maintained internal project wiki**
   - A coding or research agent ingests sources, updates the wiki, and files findings back into the repository.

4. **Project management embedded into a knowledge base**
   - Questions, decisions, milestones, and tasks are maintained alongside technical and domain context.

5. **Code-aware wiki with incremental maintenance**
   - The system understands repo docs and code structure and can update project knowledge as the repo evolves.

## 6. User Personas

### 6.1 Solo technical researcher/developer

Wants a local-first knowledge system in git that helps maintain deep technical and domain context over time.

### 6.2 AI-assisted project owner

Uses coding/research agents heavily and wants a stable markdown-and-CLI substrate agents can operate against.

### 6.3 Small open-source team

Wants a reviewable, collaborative wiki tied to a repo, with optional PR-based workflows and GitHub automation.

## 7. High-Level Architecture

Splendor consists of these major components:

1. **Repository layout and schema**
2. **CLI**
3. **Local execution engine**
4. **Ingestion pipeline**
5. **Deterministic maintenance/linting**
6. **LLM-assisted synthesis/update layer**
7. **Optional local web UI**
8. **Optional GitHub Actions automation layer**

## 8. Storage Contract

### 8.1 Source of truth

The repository contents are the source of truth.

Splendor starts **without** a required SQLite database or local index database. Optional accelerators may be introduced later, but the first implementation should rely on the filesystem and structured repo state only.

### 8.2 Storage design principle

- **Repo truth first**
- **File-based state first**
- **Optional caches/indexes later**
- **Canonical source reference first; snapshot second**

### 8.3 Why no SQLite in the initial core

- simpler mental model
- easier review and debugging
- better git transparency
- lower implementation weight
- better fit for agent use and PR workflows

### 8.4 Source-resolution model

Splendor should treat source registration as a two-part contract:

1. **Canonical reference**
   - The repo-relative path, local external path, URL, or imported identifier that names the source
     the user wants tracked.

2. **Optional storage realization**
   - A copy, symlink, pointer file, or no stored artifact at all, depending on policy and source
     type.

This is especially important for in-repo text sources. When the source already lives inside the git
workspace, the default behavior should be to track that repo file directly rather than duplicate it
into `raw/sources/`. Splendor should still be able to materialize a snapshot when the project
explicitly opts in or when the source is external to the workspace.

### 8.5 Default storage policy

Recommended defaults:

- **In-repo sources:** track the workspace file directly; do not copy by default
- **External local files:** copy into `raw/sources/` by default
- **Remote imports / fetched content:** materialize a local stored artifact by default
- **Project override:** allow repositories to opt into copying in-repo files when strict snapshot
  capture is preferred over tree cleanliness

## 9. Suggested Repository Layout

Below is a proposed baseline layout. Exact names may evolve, but the separation of concerns should remain.

```text
splendor/
  AGENTS.md
  splendor.yaml

  raw/
    sources/
    assets/
    imports/

  derived/
    ocr/
    parsed/
    metadata/
    summaries/

  wiki/
    index.md
    log.md
    concepts/
    entities/
    topics/
    sources/
    glossary/
    architecture/

  planning/
    milestones/
    tasks/
    decisions/
    questions/

  state/
    queue/
    runs/
    locks/
    manifests/

  reports/
    lint/
    health/
    ingest/

  .github/
    workflows/
```

For in-repo mode, this can live under a top-level `splendor/` directory or a configurable project subdirectory.

For companion-repo mode, this may be the root layout of the companion repository, with references back to the code repository.

## 10. Page Schema Philosophy

Splendor uses **two schema styles**.

### 10.1 Strict structured objects

Used for:
- milestones
- tasks
- decisions
- questions
- source records
- run records
- queue records

These should have strict YAML frontmatter or sidecar metadata schemas.

### 10.2 Semi-structured knowledge pages

Used for:
- concept pages
- topic pages
- synthesis pages
- source summary pages
- architecture pages

These remain markdown-first, but include standardized frontmatter for discoverability and provenance.

## 11. Core Object Schemas

## 11.1 Source record

Purpose: identify a source, its canonical reference, its storage policy, and its ingestion status.

Suggested fields:
- `schema_version`
- `kind: source`
- `source_id`
- `title`
- `source_type`
- `source_ref`
- `source_ref_kind`
- `storage_mode`
- `storage_path` (optional)
- `origin_url` (optional)
- `checksum`
- `added_at`
- `status`
- `pipeline_version`
- `derived_artifacts`
- `linked_pages`
- `last_run_id`
- `review_state`
- `materialized_at` (optional)
- `source_commit_capture` (optional nullable)
- `source_commit` (optional)

Field meanings:

- `source_ref`
  - Canonical identifier for the source the user registered.
  - For in-repo files this should usually be a repo-relative path.
- `source_ref_kind`
  - Expected initial values: `workspace_path`, `external_path`, `url`, `imported`, `stored_artifact`.
- `storage_mode`
  - Expected initial values: `none`, `copy`, `symlink`, `pointer`.
  - Current runtime support:
    - `none` for workspace-backed sources
    - `copy` for workspace-backed and external local sources
    - `pointer` for workspace-backed sources via `raw/sources/<source_id>/pointer.json`
    - `symlink` for workspace-backed sources via `raw/sources/<source_id>/<filename>`
- `storage_path`
  - Optional path to the materialized artifact under `raw/sources/` when one exists.
  - Pointer-backed sources use `raw/sources/<source_id>/pointer.json`.
  - Symlink-backed sources use `raw/sources/<source_id>/<filename>`.
- `logical_id`
  - Optional stable logical identity above the content-addressed `source_id`.
  - Workspace-backed sources use `source:<workspace-path>`, for example
    `source:docs/spec.md`, so agents can refer to a logical source across content refreshes.
- `aliases`
  - Optional stable lookup aliases for the source. Workspace-backed registrations persist the
    repo-relative path alias and expose the effective logical ID through lookup/freshness payloads.
  - These aliases do not replace content-addressed `src-...` IDs for manifests, queue records, run
    records, or generated source-summary pages.
- `source_commit_capture`
  - Optional nullable capture intent persisted separately from `source_commit`. `true` preserves an
    explicit capture request across refreshes, `false` preserves an explicit opt-out, and `null`
    means refresh uses the workspace `sources.capture_source_commit` default.
  - Legacy manifests without this field preserve positive capture intent when `source_commit` is
    already populated.
- `source_commit`
  - Optional git commit SHA captured for clean tracked workspace files when the project wants
    stronger repo-native provenance.

## 11.2 Knowledge page frontmatter

Suggested minimum fields:
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

## 11.3 Task

Suggested fields:
- `schema_version`
- `kind: task`
- `task_id`
- `title`
- `status`
- `priority`
- `milestone_refs`
- `decision_refs`
- `question_refs`
- `owner` (optional)
- `created_at`
- `updated_at`
- `depends_on`
- `source_refs`

## 11.4 Milestone

Suggested fields:
- `schema_version`
- `kind: milestone`
- `milestone_id`
- `title`
- `status`
- `target_date` (optional)
- `created_at`
- `updated_at`
- `task_refs`
- `decision_refs`
- `question_refs`

## 11.5 Decision

Suggested fields:
- `schema_version`
- `kind: decision`
- `decision_id`
- `title`
- `status`
- `decided_at` (optional)
- `supersedes`
- `source_refs`
- `related_tasks`
- `related_questions`

## 11.6 Question

Suggested fields:
- `schema_version`
- `kind: question`
- `question_id`
- `title`
- `status`
- `created_at`
- `updated_at`
- `source_refs`
- `related_tasks`
- `related_decisions`

## 11.7 Queue item

Suggested fields:
- `schema_version`
- `kind: queue_item`
- `job_id`
- `job_type`
- `status`
- `created_at`
- `updated_at`
- `attempt_count`
- `max_attempts`
- `payload_ref`
- `lease_owner`
- `lease_expires_at`
- `last_error`

## 11.8 Run record

Suggested fields:
- `schema_version`
- `kind: run`
- `run_id`
- `job_id`
- `job_type`
- `started_at`
- `finished_at`
- `status`
- `input_refs`
- `output_refs`
- `warnings`
- `errors`
- `pipeline_version`

## 12. Indexing and Logging

Karpathy’s note identifies `index.md` and `log.md` as two special files that help the user and the LLM navigate the wiki: an index for content discovery and a chronological log for what happened and when. fileciteturn0file0L63-L77 Splendor should preserve those ideas, but strengthen them with structured state.

### 12.1 `wiki/index.md`

Human-readable, content-oriented entry point to the wiki.

Responsibilities:
- list major pages by section
- provide one-line summaries
- expose important top-level navigation
- remain readable on GitHub

### 12.2 `wiki/log.md`

Append-only chronological log.

Responsibilities:
- ingests
- queries filed back into the wiki
- lint passes
- repair attempts
- major planning changes

### 12.3 Structured state alongside markdown

The log and index are useful human-facing files, but they should not be the only machine-readable state. Machine workflows should rely on records in `state/`.

## 13. Execution Model

Splendor uses a **CLI-first execution model**.

### 13.1 Primary interface: CLI

The CLI is sufficient for:
- adding sources
- ingesting sources
- querying the wiki
- running lint/health checks
- creating/updating planning objects
- inspecting queue state
- retrying failed jobs
- filing answers back into the wiki

This means an agent can operate Splendor entirely through the CLI. A local web UI is not required for core operation.

### 13.2 Secondary interface: local web server

Optional component.

Responsibilities:
- browse wiki pages
- search and navigate
- inspect planning objects
- inspect queue/runs
- add sources through a simple UI
- optionally trigger jobs

The UI is useful for humans, but not a core dependency.

### 13.3 Optional interface: GitHub Actions

GitHub Actions is a secondary automation surface, not the authoritative runtime.

Good uses:
- linting
- schema validation
- backlink/orphan checks
- scheduled retries
- optional remote ingestion
- PR comment/report generation
- nightly health checks

Not the preferred primary runtime for:
- heavy OCR workflows
- highly interactive ingestion
- large-scale semantic maintenance
- anything that becomes awkward under CI constraints

## 14. Ingestion Model

## 14.1 Core ingestion flow

1. Source is resolved to a canonical `source_ref`
2. Source manifest/record is created
3. Optional storage realization happens according to `storage_mode`
4. A queue item is created
5. A worker claims the job
6. Source content is resolved through a common source-resolution layer
7. Optional extraction happens
8. Source-summary pages are created/updated
9. Index/log are updated
10. Run record is written
11. Job is marked complete or failed

Ingestion is the source-to-summary half of the knowledge loop. It registers evidence, creates
deterministic summaries, records provenance, and leaves the workspace in a safe state. Updating
higher-level synthesis pages is a related but distinct compile/update workflow.

## 14.2 Ingestion granularity

Early versions should optimize for **one-source-at-a-time ingestion** with optional batch support later.

## 14.3 File type handling

Initial preferred formats:
- markdown
- plain text
- source code
- YAML/JSON
- HTML saved locally

## 14.4 In-repo source handling

For in-repo text sources, Splendor should default to:

- manifesting the repo-relative source path as the canonical `source_ref`
- reading from the workspace path during ingest
- validating that the current file still matches the registered checksum
- optionally recording the current git commit when available
- skipping `raw/sources/` duplication unless the project explicitly requests snapshot materialization

This keeps the repository readable while preserving deterministic provenance.

## 14.5 Source summary page policy

Source-summary pages should remain deterministic, but the rendered markdown should avoid
needlessly reproducing the full source text for files that already live in the same repository.

Recommended default behavior:

- include source metadata and provenance
- include a short preview or bounded excerpt
- link to the canonical source path
- reserve full extracted text for cases where the source is external, transformed, or otherwise not
  directly readable from the repository

Current implementation:

- workspace-backed in-repo text sources default to `excerpt`
- excerpt mode prefers claim-bearing sections such as `Core Claims`, `Design Implications`,
  `Product Experience Notes`, and `Summary`; if no such section exists, it falls back to a bounded
  opening excerpt
- copied or external text sources default to `full`
- text-bearing PDF sources are parsed through source-type dispatch, with extracted text written to
  `derived/parsed/<source-id>.txt` and linked from the source manifest via `derived_artifacts`
- image sources and image-only PDFs may use explicitly configured OCR through the deterministic
  `sidecar-text` provider, with extracted text written separately to
  `derived/ocr/<source-id>.txt`, sidecar checksum metadata written to
  `derived/metadata/<source-id>.ocr.json`, and both artifacts linked from the source manifest via
  `derived_artifacts`
- projects may set either class to `none`, `excerpt`, or `full` through
  `sources.summarize_in_repo_extracts_as` and `sources.summarize_external_extracts_as`
- when the mode is `none`, the `## Extract` section is omitted entirely
- generated source-summary pages render the registered path/source file before the canonical source
  ID so reviewers can inspect the readable source first

## 14.6 Wiki compile/update workflow

Splendor should provide an explicit source-to-synthesis workflow after ingestion. The first version
can be conservative and review-oriented:

- `splendor wiki status` reports source counts, page counts, queue state, recent runs,
  machine-generated pages, stale pages, contested pages, orphan pages, and pages needing review
- `splendor wiki suggest <source-id|title|path>` identifies concept, topic, architecture, comparison, or
  overview pages likely affected by a source
- `splendor wiki compile <source-id|title|path>` or an equivalent reviewed operation updates synthesis pages
  with auditable provenance and run state

This workflow should start with text-native sources and deterministic page-impact suggestions. The
compile step may remain human-reviewed or LLM-assisted behind explicit confirmation until the
contract is trustworthy.

Current `splendor wiki compile <source-id>` support remains intentionally non-mutating when no
target page is provided. It validates the source record and prints the review-gated contract:
inspect the source summary, review ranked maintained-page suggestions, run the ready-to-run
`wiki compile <source-id> --page <page>` preview commands, propose synthesis-page edits with
provenance/run state, keep generated source-summary pages separate from maintained synthesis pages,
and require human review before wiki synthesis is changed. `wiki suggest` exposes the same preview
commands in human and JSON output so agent handoffs do not have to stitch together command strings
manually. JSON output also carries structured `compile_preview_args` argv tokens alongside the
rendered `compile_preview_command`.

The first mutating slice is deliberately narrow. `splendor wiki compile <source-id|title|path>
--page <maintained-page>` proposes a deterministic one-page update from the generated
source-summary page into a maintained topic, concept, entity, architecture, or glossary page. The
proposal reports a unified diff, target/source-summary SHA-256 hashes, and a proposal hash. It
adds a managed `Compiled Source Evidence` section to the page body, adds the source ID to
frontmatter `source_refs`, records provenance links to the source and generated source-summary
page, and validates schema-version-1 frontmatter before reporting output. The command writes only
when the operator supplies `--apply --proposal-hash <hash>`, making apply an explicit reviewed
accept step bound to the current target and source-summary inputs. Generated source-summary pages
are rejected as compile targets.

Command output should support the workflow without becoming noisy. After `add-source`, Splendor
should print the exact next ingest command or enqueue the source for pending ingestion. After
`ingest`, it should point to the generated source-summary page and, once available, the relevant
`wiki suggest` command. After query/file-answer commands, it should clearly state whether there is a
follow-up filing or review step.

Current implementation:

- `splendor add-source <path>` registers the source and creates a pending ingest queue item for
  CLI-created sources, so `splendor ingest --pending` can continue the loop without copying the
  source ID.
- `splendor add-source --glob "pattern"` and `splendor add-source --dir path` register batches in
  deterministic path order with filename-derived titles.
- `splendor source list` and `splendor source lookup [query]` map human-readable titles, paths, and
  stable logical IDs back to canonical source IDs without renaming existing source-summary pages.
- Mutating source commands use stricter selector resolution than lookup. Direct ingest accepts exact
  source IDs, exact logical IDs, exact path aliases/source refs, or exact unambiguous titles, not
  substring matches that can silently select the wrong source.
- `splendor source refresh <source-id|title|path>` detects changed source content, registers the
  current bytes as a new canonical source version when the checksum changed, and queues ingest via
  the existing queue ledger while preserving active-lease and dead-letter protections.
  Stable logical source identities now remain constant for workspace-backed source paths across
  those content-addressed versions. Refresh also links changed versions with `supersedes` and
  `superseded_by` so health treats older workspace-backed manifests as historical records instead
  of active current-byte targets.
- `splendor source update-path <source-id|logical-id|title|path> <new-path>` repairs an active
  `none`/`copy` storage workspace-backed source manifest after a curated file moves. It validates
  that the old path is missing unless `--force` is supplied, validates that the target is a
  supported in-workspace file, rejects targets already curated by another active source, updates
  the manifest's path/logical identity fields, and reports manifest/current checksums plus next
  commands. Same-byte moves queue re-ingest for the existing source ID so generated provenance can
  refresh; changed-byte moves are reported as partial repairs and point to `source refresh`. It
  does not perform broad discovery, register uncurated files, rewrite historical run records, or
  mutate maintained synthesis pages.
- `splendor workspace refresh --changed` safely refreshes only changed curated workspace-backed
  sources by composing `source freshness` with the supersession-aware `source refresh` path. It
  reports missing or unsupported active curated workspace sources as skipped unresolved diagnostics,
  records per-source refresh failures without aborting the whole command, can ingest only refreshed
  sources' queue jobs with `--ingest`, and can rebuild `wiki/index.md` after successful targeted
  ingest with `--rebuild-index`. Valid changed sources still refresh and ingest even when unrelated
  curated sources are unresolved; the command exits non-zero while skipped sources, failed refreshes,
  or targeted ingest failures remain. JSON output reports both initial and final freshness counts
  plus skipped-source and failed-refresh diagnostics.
  `--prune-superseded` deletes old generated source-summary pages only after a current successor
  summary exists, removes stale generated-page links from the superseded source manifest, and keeps
  historical source manifests and run records valid. Unsafe prune candidates are reported with
  skip reasons instead of silently ignored. `--update-topic-refs` rewrites maintained wiki page
  `source_refs` and generated source-reference list bullets from superseded source IDs to the
  active content-addressed source version, while leaving prose and code-fence mentions untouched.
  It does not discover or register uncurated files or run mutating synthesis compile/update
  workflows.
- `splendor ingest --changed` is the focused stale-ingest repair command for checksum-drifted
  curated workspace-backed sources. It composes the freshness scan, supersession-aware source
  refresh, and targeted queue worker path so a changed source can be re-ingested even when its
  previous queue record is already `done`. It does not drain unrelated pending jobs, reports no-op
  unchanged workspaces cleanly, and reports missing-source diagnostics while continuing to process
  valid changed sources.
- `splendor pr-summary --since main` is a read-only PR handoff command. It uses local git
  diff/status from the merge base with the base ref, respects configured layout paths, and uses
  existing report files to group curated source lifecycle changes, generated source-summary pages,
  maintained wiki/topic edits, queue/run/report/derived churn, latest local lint/health report
  status, and reviewer notes that separate meaningful generated knowledge from mechanical runtime
  records. Latest maintenance status is explicitly reported as local report state rather than
  fresh validation for the current `HEAD`. `--json` emits the same summary for agent handoff.
- `splendor add-topic "Title"` scaffolds a maintained topic page under `wiki/topics/<slug>.md`
  with valid knowledge-page frontmatter, optional tags/source refs, and deterministic markdown
  templates for default synthesis, research synthesis, and issue tracking.
- `splendor ingest <source-id>` prints the generated source-summary page/run records and the next
  `splendor wiki suggest <source-id>` command, plus generated-state guidance for reviewing source
  manifests, source-summary pages, queue records, run records, and explicit reports.
- PDF ingest first uses deterministic local extraction for text-bearing PDFs. Image-only PDFs and
  image sources only enter OCR when `sources.ocr_enabled` is true; the current local provider reads
  adjacent sidecar text files named with `sources.ocr_sidecar_suffix` and writes normalized output
  under `derived/ocr/` plus sidecar checksum metadata under `derived/metadata/`.
- `splendor ingest --pending` prints the next `wiki suggest` command when exactly one source was
  ingested, or points back to `wiki status` for batch follow-up.
- `splendor wiki status` reports source, page, queue, run, review, contested, stale,
  machine-generated, invalid-page, actionable synthesis-review, and missing
  synthesis-follow-up counts, with optional JSON output.
- `splendor wiki suggest <source-id|title|path>` deterministically ranks existing synthesis pages using source
  metadata, source-summary text, frontmatter source refs, tags, source refs, and page content, with
  optional JSON output. Human and JSON output include the matching
  `splendor wiki compile <source-id> --page <page>` preview command for each suggestion, and JSON
  suggestions include structured `compile_preview_args` for agent handoff.
- `splendor wiki compile <source-id|title|path>` exposes the review-gated compile-loop contract
  when no target page is supplied, including ranked maintained-page suggestions and ready-to-run
  preview commands. With `--page <maintained-page>`, it proposes a deterministic source-summary
  evidence update and unified diff for one maintained synthesis page, and `--apply
  --proposal-hash <hash>` explicitly accepts and writes that page after frontmatter and
  proposal-hash validation.
- `splendor wiki rebuild-index` rewrites `wiki/index.md` from validated wiki page frontmatter,
  including maintained synthesis pages and generated source-summary pages, without mutating the
  pages themselves.
- `splendor query` prefers claim-bearing source-summary sections over generated metadata
  boilerplate when selecting snippets, supports tag/source filters, records those filters in JSON
  and saved snapshots, and text output points to `file-answer` when a saved query has matches.
- `splendor file-answer` prints the created page and a restrained review hint after filing.
- Multi-page, LLM-assisted, and automatic-page-selection compile/update behavior remains deferred
  to later reviewed compile-loop slices.

M13-P2 repo-discovery contracts:

- `splendor repo scan` defaults to a non-mutating candidate preview that writes no source manifests,
  wiki pages, derived artifacts, queue records, run records, or reports.
- `splendor repo scan --json` emits the same preview to stdout. Persisting a discovery report
  requires `--report PATH`, and that path writes only report JSON.
- Mutating registration from scan requires `--apply` plus either `--class ...` or `--all`; the bare
  command says it is preview-only and prints the explicit apply command.
- Repo scan supports class filters, include/exclude patterns from `splendor.yaml`, optional root
  `.splendorignore` project-specific ignore patterns, and large candidate-set guards before
  registration. Exclude patterns win over include patterns, and class filters apply after
  include/exclude filtering.
- Broad registration refuses large candidate sets unless the operator passes
  `--allow-large-apply` after reviewing the preview/report.
- `splendor.yaml` supports `sources.include_patterns`, `sources.exclude_patterns`, and
  `sources.repo_scan_default_classes`; the default class policy favors documentation/curated
  knowledge over all supported files.
- `splendor source freshness` reports curated sources whose canonical file content differs from the
  manifest checksum and includes source IDs, titles, paths, freshness status, manifest/current
  checksums where available, historical source-version status for paths already covered by a current
  manifest, and exact next commands. The default command is non-mutating; `--json` emits
  machine-readable output and `--report PATH` writes only an explicit freshness report.
- `brief --agent-context` leads with project state, stale/contested/actionable items, and ranked
  next actions before metadata.
- `splendor suggest-next [goal]` ranks work from open tasks, stale sources, failed jobs, missing
  synthesis, contested/review-needed pages, maintenance reports, and goal matches. `--json` emits a
  machine-readable handoff payload.

Release-readiness boundary:

- `v0.2.0` evaluation release readiness treats content-addressed source IDs as the persisted
  compatibility contract.
- readable paths, titles, source refs, and logical IDs are lookup and display aids above that
  compatibility contract; generated source-summary pages and run provenance still use `src-...`
  identifiers.
- lint checks present workspace-backed logical IDs and aliases so stale or hand-edited manifests do
  not create conflicting exact source identities.
- generated source-summary pages, queue records, run records, derived artifacts, and explicit
  reports are committed when they explain a reviewed workspace update; failed or exploratory local
  reports can remain local.
- issue #72's desired stable logical source identity and source-supersession layers have started
  with workspace-backed `source:<path>` aliases plus `supersedes`/`superseded_by` source-version
  links. The safe workspace refresh path over curated workspace-backed sources has also landed,
  including explicit superseded source-summary pruning and maintained-page source-ref migration.
  The `ingest --changed` repair path handles checksum-drifted curated workspace sources whose
  previous queue records are already done, and the `pr-summary` surface provides a read-only local
  PR handoff over that generated-state churn.
- issue #94's broader source-identity question is materially addressed for curated
  workspace-backed sources by the same contract: logical IDs and aliases are stable selectors above
  canonical `src-...` records, content edits become superseded source versions, freshness reports
  keep checksum drift separate from identity, `source update-path` preserves the original logical
  selector while adding the new path alias for intentional moves, and maintained topic refs can be
  migrated after refreshed successor summaries exist. This does not require a schema-version change
  or a canonical source-ID migration.
- issue #79 tracked the reviewed mutating compile/update workflow from #41; `M15-P1.1`,
  `M15-P1.2`, and `M15-P1.3` now represent and disposition the one-page proposal/apply path.
- `docs/v1_release_handoff.md` remains the historical v1-style handoff checklist for validation
  and GitHub metadata expectations, but the immediate evaluation release target is `v0.2.0`.

Later optional support:
- additional OCR providers
- image captioning or metadata extraction
- audio/transcript flows

## 14.7 OCR/LLM-assisted extraction

For harder formats, ingestion may optionally invoke:
- OCR
- image description/captioning
- metadata extraction
- summary generation

These outputs should be stored as **derived artifacts**, not mixed directly into raw source files.
Current OCR support is explicitly configured and local: `sources.ocr_enabled: true` with
`sources.ocr_provider: sidecar-text` reads UTF-8 sidecar text next to the resolved source artifact
using `sources.ocr_sidecar_suffix`, records the resulting artifact under `derived/ocr/`, and records
sidecar ref/checksum metadata under `derived/metadata/` so sidecar changes invalidate no-op ingest.
For copied external sources, sidecar lookup first checks next to the stored source artifact and then
next to the original local source path. Unconfigured, missing-sidecar, invalid UTF-8, and empty OCR
text cases fail with deterministic one-line ingest errors.

## 15. Idempotency and Atomicity

This is a foundational requirement.

Splendor must be able to tell whether a source:
- has never been ingested
- is partially ingested
- failed ingestion
- was ingested under an older pipeline version
- needs repair or re-ingestion

### 15.1 Source identity

Source identity should include:
- stable source path or logical ID
- checksum/content hash
- pipeline version
- ingestion mode/profile

### 15.2 Re-ingestion rule

A source should not be re-ingested merely because it exists in the repo. Re-ingestion should be triggered only when:
- the source is new
- ingestion is incomplete/failed
- the pipeline version changed
- the user explicitly requests re-ingestion
- a repair job targets the source
- a source refresh detects changed content and registers the current source version

PR handoff summarization should not trigger re-ingestion. `splendor pr-summary --since main`
observes local git state and existing report artifacts only; it does not refresh sources, enqueue
jobs, run maintenance checks, or write reports.

## 16. Queue Model

Splendor should use a **durable work ledger**, not an overengineered distributed queue.

### 16.1 Requirements

- append work item
- claim work item
- record attempt
- write result
- retry with backoff
- dead-letter after threshold
- inspect/retry manually

Queue backoff is persisted on the queue item with `next_attempt_at`. Exhausted ingest jobs move to
the terminal `dead_letter` status and require explicit operator action before another attempt.

### 16.2 Queue persistence

Initial queue persistence should be file-based under `state/queue/`.

### 16.3 Job types

Initial job types:
- `ingest_source`
- `lint_wiki`
- `refresh_page`
- `repair_ingest`
- `update_index`
- `update_log`
- `query_and_file`
- `validate_schema`

### 16.4 Late-stage UI

A queue page in the local UI is desirable, but not required for MVP.

## 17. Query Model

## 17.1 Querying

Users and agents query the wiki rather than raw sources by default.

Initial query path:
1. inspect index/navigation metadata
2. locate relevant pages
3. synthesize answer
4. cite page/source provenance
5. optionally file answer back into the wiki

Query is the context-selection path, not the only knowledge-maintenance path. Useful answers should
be fileable, and newly ingested sources should have a separate source-impact path that helps update
the durable synthesis pages.

### 17.2 Query outputs

Initial output forms:
- terminal-friendly markdown/text
- structured JSON
- markdown page filed into the wiki

Later optional forms:
- tables
- slide decks
- charts
- reports

Query snippets should favor claim-bearing source text over generated metadata. For source-summary
pages, sections such as `Core Claims`, `Design Implications`, `Product Experience Notes`, and the
source extract should outrank frontmatter-derived facts, provenance boilerplate, and generic
machine-generated labels.

Current query output includes any active deterministic filters. `splendor query --tag <tag>`
restricts matches to wiki pages carrying all requested tags, and
`splendor query --source <source-id|title|path>` resolves the source filter to canonical source
IDs before returning wiki or planning records whose `source_refs` intersect those IDs. Exact
readable path filters include all known content-addressed versions for that path until stable
logical source identities exist. Filter-only source lookup is allowed so agents can ask which pages
reference a known source without inventing a search phrase.

### 17.3 Project briefing

Splendor should support a briefing workflow for humans and agents entering an existing repository.
A briefing command or UI view should assemble:

- relevant wiki pages for a stated goal
- active planning tasks, questions, decisions, and milestones
- recent ingest, query, lint, and health state
- source-backed claims and provenance pointers
- stale, contested, machine-generated, or unreviewed pages
- likely next actions

This is the natural bridge between repository-local memory and limited model context. Search finds
records; a briefing prepares compact working context for a session.

Current implementation:

- `splendor brief [goal]` assembles a terminal-friendly and JSON project brief from deterministic
  query matches, wiki status, active planning records, recent sources/runs, latest lint/health
  reports, the last query snapshot, ranked authority docs, and likely next actions.
- `splendor brief --agent-context [goal]` renders the same deterministic state as a compact
  coding-agent handoff with relevant matches, source refs, wiki status, active planning records,
  ranked authority docs, recent sources/runs, maintenance reports, warnings, and ranked suggested
  actions.
- `splendor suggest-next [goal]` renders the ranked action subset directly. It is read-only and
  deterministic, and ranks source freshness, queue failures or pending work, stale/contested or
  review-needed pages, missing synthesis follow-up, task-relevant authority docs, active planning
  records, recent maintenance reports, and query matches for the optional goal.
- Authority docs come from `briefing.authority_documents` in `splendor.yaml` and optional
  maintained wiki page frontmatter (`authority_role`, `authority_freshness`, and
  `authority_scope`). Generated source-summary pages are excluded from maintained authority
  ranking.
- Briefing is read-only and does not replace `splendor query`; query finds records, while briefing
  packages the surrounding project state needed to resume work.

## 18. Search Model

### 18.1 Early search

Early versions should use deterministic local search over markdown/filesystem metadata plus the wiki index.

### 18.2 Future search

A later optional search accelerator may include:
- BM25
- hybrid lexical + vector search
- re-ranking
- optional local index database

But this should not be required for the smallest opinionated core.

## 19. Code Awareness

Splendor should understand the repository itself as a first-class source domain.

Potential code-aware source classes:
- README/docs
- ADRs/design docs
- config files
- schemas
- code comments/docstrings
- tests
- issue exports
- PR summaries
- release notes

Potential code-aware capabilities:
- map code modules to wiki pages
- detect when changed code should trigger wiki maintenance
- summarize architecture drift
- relate decisions/tasks to files/modules

This is an important differentiator for Splendor.

## 20. Human Review Model

Human review should be configurable, but early implementation should choose **one primary review path**.

### 20.1 Possible review modes

1. **Direct apply**
   - Splendor writes changes directly.
   - Suitable for trusted local workflows.

2. **Local propose-before-commit**
   - Splendor stages changes locally for human review before commit.

3. **PR-based review**
   - Splendor writes changes to a branch and opens or updates a PR.

### 20.2 Recommendation for initial implementation

Start with **local propose-before-commit** or **PR-based review**, but only one.

Given your priorities, PR-based review is attractive because:
- it integrates with GitHub review habits
- it preserves a clean review trail
- it works naturally with GitHub Actions linting

However, local propose-before-commit is simpler to implement and avoids requiring GitHub for the normal flow.

### 20.3 Recommendation on CI after human approval

Even when changes are reviewed locally by a human, CI should still run after the commit lands. That does **not** require the change to go through a PR in all setups. A repo can run GitHub Actions on `main` as well. So:
- PR review is useful for review quality and gating
- CI on `main` is sufficient for basic post-merge validation
- PRs are not strictly required for correctness, only for workflow quality and collaboration

## 21. GitHub Integration Philosophy

Splendor is GitHub-powered, not GitHub-dependent.

### 21.1 Optional GitHub-native features worth supporting

- PR-based review workflows
- Actions-based linting and health checks
- scheduled maintenance
- issue/PR ingestion into the wiki
- commenting reports on PRs
- release-triggered wiki refreshes
- repo dispatch/event-driven jobs

These should be treated as **strong optional features**, not mandatory architectural assumptions.

## 22. Deterministic Maintenance and Linting

Not all maintenance should use LLMs.

### 22.1 Deterministic checks

- schema validation
- frontmatter validation
- orphan page detection
- broken internal links
- duplicate page IDs
- queue integrity
- stale run references
- unresolved source references

Current health output is also a repair guide where Splendor has a narrow, existing command for the
problem. Maintenance issues may include a `remediation_hint` in JSON, human stdout, and Markdown
reports. Missing active workspace source paths point to `source update-path` plus `source
freshness`; checksum drift points to `source refresh`, `ingest --pending`, or `ingest --changed`;
queue failure diagnostics point to `queue retry` or `repair ingest`. Unknown source provenance
references remain diagnostic-only until a safe provenance repair design exists.

### 22.2 LLM-assisted maintenance

- contradiction detection
- missing concept/entity suggestions
- stale synthesis warnings
- proposed cross-links
- proposed coverage gaps
- suggested external research questions

## 23. Conflict Handling

When new material contradicts existing wiki content, Splendor should avoid silent overwrites.

Initial desired behavior:
- annotate contradiction
- preserve provenance to both claims
- optionally open a review task
- mark pages or sections as contested when appropriate

## 24. Policy and Guardrails

Splendor should support project-specific policy rules.

Examples:
- review-required sources
- forbidden source classes
- redaction rules
- citation requirements
- source-trust tiers
- allowed model/provider settings

This is especially important for sensitive or domain-heavy projects.

## 25. CLI Surface

An illustrative early CLI might include commands such as:

```bash
splendor init
splendor add-source path/to/file.md
splendor ingest source-id
splendor ingest --pending
splendor wiki status
splendor wiki suggest source-id
splendor wiki compile source-id
splendor query "What changed in the scraping policy?"
splendor brief "continue scraping-policy work"
splendor file-answer --from-last-query
splendor lint
splendor health
splendor queue inspect [job-id]
splendor queue retry job-id
splendor repair ingest source-id
splendor task create
splendor milestone create
splendor decision create
splendor question create
splendor serve
```

Exact command design may evolve, but the CLI should remain the primary operational contract.

## 26. Local Web UI

Early web UI should be intentionally modest.

### Early capabilities
- page browsing
- search/navigation
- page backlinks/related links if available
- planning object lists/detail pages
- read-only status overview for source counts, page counts, queue/runs state, review state, and
  latest log entries
- source detail pages showing source metadata, generated summary page, ingest run, provenance, and
  affected synthesis-page suggestions
- source add form
- basic queue/runs page

The web UI should make generated versus maintained pages visible without requiring raw frontmatter
inspection. Users should be able to distinguish generated source summaries, draft synthesis,
reviewed synthesis, contested pages, and stale pages while browsing or searching.

Current implementation includes read-only `/status` and `/sources/{source-id}` pages layered on
the CLI wiki status/suggest contracts. They expose source/page/queue/run/review counts, source
manifests, linked source-summary pages, latest ingest run state, and deterministic affected
synthesis-page suggestions without adding mutating web actions. It also includes read-only
`/planning`, `/planning/{kind}`, `/runs`, and `/queue` pages that list durable planning and runtime
records and link planning rows back to their markdown detail pages.

### Avoid early
- heavy collaborative editing
- complex permissions
- hosted multi-user deployment
- large SPA complexity without product need

## 27. Configuration

Splendor should be configured via a root config file, e.g. `splendor.yaml`.

Likely configuration domains:
- paths/layout
- model/provider settings
- ingestion defaults
- OCR settings
- review mode
- queue retry policies
- planning schema conventions
- GitHub integration toggles
- policy rules

Current source settings:
- `sources.capture_source_commit`: default git commit capture policy for workspace sources when a
  source manifest has `source_commit_capture: null`, default `true`
- `sources.ocr_enabled`: opt-in OCR/image extraction toggle, default `false`
- `sources.ocr_provider`: OCR provider name, currently `sidecar-text`
- `sources.ocr_sidecar_suffix`: sidecar suffix appended to the resolved source path, default
  `.ocr.txt`
- `sources.include_patterns`: optional workspace-root-relative POSIX glob patterns that define
  repo-scan candidate inclusion
- `sources.exclude_patterns`: optional workspace-root-relative POSIX glob patterns that skip
  generated/noisy paths; exclude matches win over include matches
- `sources.repo_scan_default_classes`: class policy for non-mutating candidate discovery, applied
  after include/exclude filtering, default `["documentation"]`

Repo scan should skip Git-ignored files, root `.splendorignore` project-specific ignores, Splendor
state/output directories, dependency directories, build artifacts, local-agent directories, and
other generated paths by default unless a future explicit override flag documents the extra churn.
Class filters narrow the already-filtered candidate set; they should not override excludes. The
default class policy should bias toward documentation and curated knowledge over all supported
files.

## 28. Minimum Opinionated Core

The smallest opinionated core should be:

1. repository layout + schema conventions
2. source records
3. knowledge page frontmatter
4. operational state/runs/queue
5. `index.md` and `log.md`
6. CLI
7. one-source-at-a-time ingestion
8. deterministic source-summary generation
9. deterministic lint
10. planning objects
11. local query path
12. source-impact suggestions and a reviewable compile/update loop
13. project briefing
14. dogfood workflow polish for add-source, ingest, query, and review handoffs
15. optional file serving/browsing later

## 29. Acceptance Criteria for the Core Product

Splendor should be considered successful at the product-spec level if it can do the following reliably:

1. initialize a repo or subdirectory as a Splendor wiki
2. curate a source and create stable source metadata
3. ingest a source and create a stable source-summary page
4. identify or update affected synthesis pages through a reviewable compile/update path
5. avoid duplicate accidental re-ingestion
6. record queue/job/run state durably
7. query the wiki via CLI
8. assemble a compact project briefing for a goal
9. guide the user through add-source, ingest, query, and review handoffs without requiring hidden
   state or copied long IDs
10. create and query tasks/milestones/decisions/questions
11. lint the repo deterministically
12. operate locally without GitHub
13. optionally integrate with GitHub Actions for maintenance
14. preview repo discovery without mutating manifests or wiki pages
15. report stale curated sources and actionable next commands

## 30. Open Design Questions

These are not blockers to the spec, but should remain visible:

1. exact branch/review strategy for release tags after the initial v1 handoff
2. whether source manifests live alongside raw files or centrally in `state/`
3. exact page taxonomy naming
4. whether code files are ingested directly or via projection/snapshot policies
5. how aggressively to auto-update central synthesis pages
6. exact level of provenance granularity at the paragraph/claim level
7. whether a companion-repo linking model needs a first-class schema element
8. post-v1 refinements to generated source-summary policy for readable in-repo markdown and code
   files, after the v1 default of concise claim-bearing excerpts has been exercised in real repos
9. richer authority lifecycle policy for living planning docs after the initial M14-P4.1 metadata
   and task-oriented brief ranking has been exercised in real repos

## 31. Summary Product Statement

**Splendor turns curated project sources, planning state, and review signals into an agent-ready
context layer with provenance, freshness, contradictions, next actions, and reviewable synthesis.**
