# Splendor Product Specification

## 1. Overview

**Splendor** is a local-first, git-native, schema-driven knowledge compiler for code-and-research repositories. It turns a software project and its surrounding research materials into a maintained, queryable, reviewable project wiki composed primarily of markdown files, with structured provenance, planning objects, and incremental LLM-assisted synthesis.

The product is inspired by the LLM Wiki pattern: a persistent wiki that is continuously updated as new source material arrives, instead of re-deriving knowledge from raw documents at query time. In Splendor, that pattern is adapted specifically for software projects that require substantial research, domain knowledge, technical decision tracking, and project planning. The uploaded concept note emphasizes the persistent wiki as the central compounding artifact, with raw sources remaining immutable and the LLM maintaining the synthesized layer. fileciteturn0file0L6-L18 fileciteturn0file0L35-L43

## 2. Product Goals

### Core goals

1. **Maintain a persistent project wiki in git**
   - The wiki lives either inside the code repository or in a companion repository.
   - The wiki is primarily markdown and optimized for GitHub readability and reviewability.

2. **Support incremental source ingestion**
   - New sources are added to the repository and processed into structured wiki updates.
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
- **Structured provenance over opaque synthesis**
- **Deterministic maintenance where rules suffice**
- **LLMs for semantic work, not for every operation**
- **Optional GitHub-native acceleration, not hard platform lock-in**

## 4. Core Conceptual Model

Splendor has five conceptual layers.

### 4.1 Sources

Immutable source artifacts that represent the project’s evidence base.

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

The source layer is append-oriented. Sources are not mutated by LLM workflows.

Splendor now defaults to workspace-backed registration for in-repo files and materialized copies
for external local files. Materialization under `raw/sources/` remains useful for external and
unstable inputs, but it is too blunt for repositories whose markdown, code, and configuration files
already live inside git. The source model therefore distinguishes between:

- the **canonical source reference** the user means Splendor to track
- the **storage policy** Splendor applies to make that source available to the pipeline
- any optional **materialized snapshot or pointer artifact** Splendor creates for provenance,
  portability, or repairability

### 4.2 Derived Extraction Artifacts

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

### 4.3 Knowledge Pages

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

### 4.4 Operational Ledger

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

### 4.5 Planning Objects

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
    - `symlink` remains schema-visible but unimplemented
- `storage_path`
  - Optional path to the materialized artifact under `raw/sources/` when one exists.
  - Pointer-backed sources use `raw/sources/<source_id>/pointer.json`.
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
8. Relevant wiki pages are created/updated
9. Index/log are updated
10. Run record is written
11. Job is marked complete or failed

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
- copied or external text sources default to `full`
- projects may set either class to `none`, `excerpt`, or `full` through
  `sources.summarize_in_repo_extracts_as` and `sources.summarize_external_extracts_as`
- when the mode is `none`, the `## Extract` section is omitted entirely

Later optional support:
- PDF
- image-based sources
- OCR-derived flows
- audio/transcript flows

### 14.6 OCR/LLM-assisted extraction

For harder formats, ingestion may optionally invoke:
- OCR
- image description/captioning
- metadata extraction
- summary generation

These outputs should be stored as **derived artifacts**, not mixed directly into raw source files.

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
splendor query "What changed in the scraping policy?"
splendor file-answer --from-last-query
splendor lint
splendor health
splendor queue list
splendor queue retry job-id
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
- source add form
- basic queue/runs page later

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

## 28. Minimum Opinionated Core

The smallest opinionated core should be:

1. repository layout + schema conventions
2. source records
3. knowledge page frontmatter
4. operational state/runs/queue
5. `index.md` and `log.md`
6. CLI
7. one-source-at-a-time ingestion
8. deterministic lint
9. planning objects
10. local query path
11. optional file serving/browsing later

## 29. Acceptance Criteria for the Core Product

Splendor should be considered successful at the product-spec level if it can do the following reliably:

1. initialize a repo or subdirectory as a Splendor wiki
2. add a source and create stable source metadata
3. ingest a source and update the wiki incrementally
4. avoid duplicate accidental re-ingestion
5. record queue/job/run state durably
6. query the wiki via CLI
7. create and query tasks/milestones/decisions/questions
8. lint the repo deterministically
9. operate locally without GitHub
10. optionally integrate with GitHub Actions for maintenance

## 30. Open Design Questions

These are not blockers to the spec, but should remain visible:

1. exact branch/review strategy for the initial release
2. whether source manifests live alongside raw files or centrally in `state/`
3. exact page taxonomy naming
4. whether code files are ingested directly or via projection/snapshot policies
5. how aggressively to auto-update central synthesis pages
6. exact level of provenance granularity at the paragraph/claim level
7. whether a companion-repo linking model needs a first-class schema element

## 31. Summary Product Statement

**Splendor turns a code repo and its research materials into a maintained, queryable, reviewable project wiki — with provenance, tasks, decisions, and incremental LLM-assisted synthesis.**
