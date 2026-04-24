# Splendor Roadmap: MVP to v1

## 1. Roadmap Overview

This roadmap translates the Splendor product direction into staged delivery milestones from MVP to v1. It assumes the product is:

- local-first
- git-native
- CLI-first
- schema-driven
- GitHub-powered but not GitHub-dependent
- designed for code-and-research repositories

The roadmap is deliberately conservative at the start. The goal is not to ship a maximal “LLM wiki platform,” but to ship a trustworthy, repairable, agent-friendly core that compounds value over time.

## 2. Guiding Delivery Principles

1. **Earn complexity**
   - Start with file-based state and deterministic logic.
   - Add optional acceleration layers later.

2. **Prioritize trust over flash**
   - Provenance, idempotency, and recoverability come before richer UI.

3. **CLI first**
   - The CLI is the system contract.
   - The web UI is layered on top later.

4. **One primary review path at first**
   - Avoid multiple workflow modes in the first implementation.
   - Keep configuration and mental overhead contained.

5. **GitHub features should be additive**
   - They should improve the system, not define it.

## 2.5 Planning notation

Roadmap notation uses two levels:

- parent milestone slices such as `M6-P1`
- concrete PR sub-slices such as `M6-P1.1`, `M6-P1.2`, and `M6-P2.1`

The parent slice names the roadmap unit. The dotted sub-slice names the specific PR that advances
that unit when the work spans more than one pull request.

## 3. Release Shape

### MVP
A trustworthy local CLI with file-based state, source ingestion, wiki updates, planning objects, and deterministic linting.

### v0.x
A strengthening phase that adds better provenance, smarter maintenance, code awareness, and initial GitHub-native workflows.

### v1.0
A coherent, documented product with optional web UI, durable queue workflows, stronger search/navigation, and a stable extension/integration story.

---

## Milestone 0 — Product framing and repo skeleton

### Goal
Create the project skeleton and lock the product contract before implementing workflows.

### Deliverables
- repository initialized
- packaging/tooling baseline
- top-level docs
- draft schemas
- initial directory layout
- design docs for core components

### Key outputs
- `README.md`
- `docs/product-spec.md`
- `docs/roadmap.md`
- `splendor.yaml` example
- initial `AGENTS.md`
- schema docs for:
  - source
  - page frontmatter
  - task
  - milestone
  - decision
  - question
  - queue item
  - run record

### Notes
This milestone is mostly documentation and scaffolding, but it is important. It gives Codex/agents and humans a stable frame.

### Exit criteria
- the product vocabulary is stable enough to begin implementation
- the repo layout exists
- schemas are written at least in draft form

---

## Milestone 1 — MVP core: local-first wiki initialization and source registry

### Goal
Make Splendor able to initialize a wiki and register sources locally in a disciplined, schema-driven way.

### Scope
- CLI foundation
- init command
- source add command
- source record generation
- repository layout creation
- file-based state conventions

### Deliverables
- `splendor init`
- `splendor add-source <path>`
- creation of baseline repo directories
- source checksum computation
- source manifest/record writing
- initial `wiki/index.md` and `wiki/log.md`
- schema validation for source records

### Key design choices
- no SQLite
- no web UI
- no OCR
- no GitHub dependency
- repo filesystem is the source of truth

### Exit criteria
- a user can initialize Splendor in a repo/subdir
- a user can add a source and see a durable source record
- duplicate identical source registration is handled cleanly
- source metadata is deterministic and validated

---

## Milestone 2 — MVP core: one-source-at-a-time ingestion

### Goal
Support the first useful end-to-end ingestion flow.

### Scope
- queue item creation for ingestion
- worker execution in local CLI context
- initial page generation/update behavior
- run records
- idempotent ingest decisions
- update of index/log

### Deliverables
- `splendor ingest <source-id>`
- `splendor ingest --pending`
- file-based queue and run state
- source summary page generation
- update of one or more wiki pages
- append-only log entry generation

### MVP constraints
- start with text-native sources only:
  - markdown
  - txt
  - yaml/json
  - code files
- batch mode can be very simple or omitted
- semantic updates can initially be modest:
  - create source summary
  - update a small number of related pages
  - update index/log

### Important requirements
- do not accidentally re-ingest unchanged sources
- support clear failed state
- support retryable queue items
- record pipeline version in runs

### Exit criteria
- a user can ingest a source end to end
- the wiki changes in a stable, traceable way
- failed ingests do not corrupt state
- repeated ingest commands behave predictably

### Follow-on architecture correction

The initial MVP intentionally uses a simple copy-based source materialization model. That choice is
acceptable for bootstrapping, but it is not the right steady-state design for repositories whose
primary sources already live in git. The next architecture correction should split:

- canonical source reference
- storage policy
- optional materialized artifact

That refactor should happen before richer source handling expands, so all later source types build
on the same resolver contract.

---

## Milestone 3 — MVP core: query and planning objects

### Goal
Make Splendor genuinely useful as both a knowledge base and a project-management substrate.

### Scope
- basic query over the wiki
- planning object creation and listing
- markdown rendering of structured planning objects
- query output optionally filed back into the wiki

### Deliverables
- `splendor query "<question>"`
- `splendor task create`
- `splendor milestone create`
- `splendor decision create`
- `splendor question create`
- `splendor task list`
- `splendor milestone list`
- `splendor query --json`
- optional `splendor file-answer`

### Notes
This is the point where Splendor starts to feel distinct from a generic RAG wrapper. The planning objects are part of the core identity.

### Exit criteria
- users can query the maintained wiki via CLI
- users can create structured planning objects
- planning objects are stored in git-friendly markdown with machine-readable frontmatter
- planning objects can be listed and filtered at least minimally

### Planned PR slices
- `M3-P1` Planning-object create/list commands
- `M3-P2` Query CLI plus `query --json` (implemented)
- `M3-P3` Optional file-answer workflow

### Milestone 3 status

`M3-P1` and `M3-P2` are implemented. The next planned Milestone 3 PR is `M3-P3`, which adds the
optional file-answer workflow on top of the deterministic local query path.

---

## Milestone 4 — MVP core: deterministic lint and health checks

### Goal
Ship the first strong maintenance layer without overusing LLMs.

### Scope
- schema validation
- orphan detection
- broken internal links
- duplicate ID detection
- unresolved source refs
- queue integrity checks

### Deliverables
- `splendor lint`
- `splendor health`
- machine-readable and human-readable reports
- report files under `reports/`

### Recommended checks
- invalid frontmatter
- broken wiki links
- page missing required fields
- source refs pointing nowhere
- task/milestone/decision/question ref integrity
- queue items with invalid transitions
- stale leases or unfinished runs

### Exit criteria
- a user can run deterministic health checks locally
- failures are actionable
- linting can run in CI later with minimal extra work

### Planned PR slices
- `M4-P1` Lint/health command framework and report writing
- `M4-P2` Wiki/planning/source integrity checks
- `M4-P3` Queue/run integrity checks and repair diagnostics

### Milestone 4 status

`M4-P1`, `M4-P2`, and `M4-P3` are implemented. Milestone 4 now covers bootstrap linting,
wiki/planning/source integrity checks, and queue/run repair diagnostics through the shared
maintenance reporting layer.

That work now hands off into Milestone 5, starting with MVP docs, quickstart flow, and an example
workspace in `M5-P1`.

---

## Milestone 5 — MVP release hardening

### Goal
Ship a first public MVP that is stable enough for real project use.

### Scope
- docs polish
- examples
- better errors
- test coverage
- packaging
- import/export polish
- config cleanup

### Deliverables
- installation docs
- quickstart
- example wiki repo
- example companion-repo setup
- example AGENTS.md
- tests for:
  - init
  - add-source
  - ingest
  - query
  - lint
  - planning commands

### Exit criteria
- external users can install and run the MVP
- the MVP is reliable on at least one real project
- the CLI surface is coherent and documented

### Planned PR slices
- `M5-P1` MVP docs, quickstart, and example workspace
- `M5-P2` MVP hardening: coverage, errors, packaging, polish

### Milestone 5 status

`M5-P1` and `M5-P2` are implemented. The repository now has an MVP entrypoint README, a dedicated
quickstart, companion-repo setup guidance, a committed in-repo example workspace, broader
regression coverage for operational edge cases, consistent one-line CLI error output, and a
package-install smoke path that validates the built CLI.

`M6-P1` is implemented through `M6-P1.1` and `M6-P1.2`, and `M6-P2.1` is now implemented on top of
that foundation. The repository now persists machine-generated and contested review states for
source-summary pages, structured source/page/run provenance in ingest artifacts, contradiction
annotations plus linked review tasks for explicit conflicts, richer query metadata, and
deterministic lint/health validation for those cross-links.

- Previous completed PR sub-slice: `M7-P1.1`
- Current planned slice: `M7-P2`
- Current PR sub-slice: `M7-P2.1`
- Current PR lifecycle: `branch=in-progress; main=merged`
- Next planned slice: `M8-P1`
- Next planned PR sub-slice: `M8-P1.1`

The current PR sub-slice is `M7-P2.1`, under parent slice `M7-P2`, which moves the roadmap forward
into repo refresh and architecture/topic linkage. The lifecycle marker means `M7-P2.1` is in
progress on feature branches and merged once the same committed state is observed on `main`.

---

## Milestone 6 — Post-MVP: stronger provenance and review state

### Goal
Deepen trustworthiness of the wiki and make generated knowledge easier to audit.

### Scope
- page review states
- provenance enrichment
- contradiction annotations
- better run/source/page linking

### Deliverables
- review states such as:
  - draft
  - machine-generated
  - human-reviewed
  - contested
  - stale
- stronger source-to-page linking
- automatic creation of review tasks for contradictions
- improved provenance display in CLI output

### Why this matters
This milestone is especially important for sensitive, policy-heavy, or research-heavy domains.

### Exit criteria
- users can inspect why a page says what it says
- contested knowledge is surfaced instead of silently merged
- provenance is visible enough to support trust and debugging

### Planned PR slices
- `M6-P1` Review-state and provenance model expansion
- `M6-P2` Contradiction surfacing and review-task linkage

### Current PR sub-slices
- `M6-P1.1` Schema groundwork and PR completion-gate codification
- `M6-P1.2` Ingest, wiki rendering, CLI/query, and lint/health provenance threading

### Milestone 6 status

`M6-P1` and `M6-P2.1` are implemented. This milestone now includes explicit contradiction
annotations on contested source-summary pages plus linked review tasks created during ingest.

---

## Milestone 6.5 — Post-MVP: source-resolution and storage-policy refactor

### Goal
Make source handling repo-native by default without weakening provenance for external or unstable
sources.

### Scope
- split canonical source reference from storage realization
- default in-repo files to workspace-backed registration
- preserve copy, pointer, and symlink options where projects need stronger materialization
- reduce source-summary duplication for in-repo text sources

### Deliverables
- a source resolver abstraction
- revised source manifest schema
- configuration for storage policy defaults
- CLI overrides for source storage behavior
- manifest migration path for older workspaces
- config-driven source-summary rendering that defaults in-repo text sources to excerpts and
  external/copied text sources to fuller extracts

### Exit criteria
- in-repo docs and code stop being duplicated into `raw/sources/` by default
- external sources still get durable materialization when appropriate
- workspace-backed sources can optionally materialize deterministic pointer artifacts under
  `raw/sources/<source_id>/pointer.json`
- workspace-backed sources can optionally materialize symlink artifacts under
  `raw/sources/<source_id>/<filename>`
- ingest reads through one resolver interface regardless of source origin
- source-summary pages remain deterministic while becoming less noisy

### Historical implementation sequence
- `SR-1` Docs and contract alignment
- `SR-2` Schema and config scaffolding
- `SR-3` Source resolver abstraction
- `SR-4` `add-source` default behavior switch
- `SR-5` Migration and polish
- `SR-6` Source-summary rendering policy
- `SR-7` Pointer storage mode
- `SR-8` Optional symlink mode
- `SR-9` Materialization workflow polish

---

## Milestone 7 — Post-MVP: code awareness

### Goal
Make Splendor truly repo-aware rather than document-only.

### Scope
- treat repo documentation and code structure as first-class inputs
- connect files/modules to wiki pages
- detect repo changes that should trigger maintenance

### Deliverables
- code/doc source classification
- file/module references in wiki pages
- architecture/topic pages tied to repo structure
- optional changed-files-driven refresh suggestions
- commands such as:
  - `splendor repo scan`
  - `splendor repo refresh`

### Notes
This milestone is a likely differentiator for Splendor versus more generic LLM wiki tools.

### Exit criteria
- Splendor can reason about the code repo itself
- repo changes can drive meaningful wiki maintenance
- architecture understanding is materially improved

### Planned PR slices
- `M7-P1` Repo scan and code/doc source classification
- `M7-P2` Repo refresh and architecture/topic linkage

---

## Milestone 8 — Post-MVP: optional GitHub Actions integration

### Goal
Add strong optional GitHub-powered features without making GitHub mandatory.

### Scope
- CI lint
- scheduled maintenance
- optional PR-centric workflows
- optional action-triggered ingestion/refresh

### Deliverables
- reusable GitHub Actions workflows for:
  - lint
  - health
  - scheduled retries
  - optional ingest
- docs for required secrets and least-privilege setup
- sample PR workflow for review mode
- branch/PR conventions if PR-based review is chosen

### Good optional features
- run `splendor lint` on PRs
- nightly `splendor health`
- open/update PRs for machine-generated proposed changes
- append maintenance reports to job artifacts or PR comments

### Exit criteria
- a GitHub-heavy user can adopt strong GitHub-native workflows
- a non-GitHub user is not blocked by any of this

### Planned PR slices
- `M8-P1` GitHub Actions lint/health integration
- `M8-P2` Optional PR-centric generated-change workflows

---

## Milestone 9 — Post-MVP: local web UI v0

### Goal
Provide a modest but useful human UI without changing the system’s center of gravity away from the CLI.

### Scope
- browse pages
- simple search
- navigate planning objects
- add source through UI
- inspect job/runs at a basic level

### Deliverables
- `splendor serve`
- page detail views
- index/topic navigation
- planning pages and simple filters
- add-source form
- basic runs/queue page if feasible

### Explicit constraints
- not a full collaborative editor
- not a hosted product
- not a complex SPA unless justified

### Exit criteria
- a human can comfortably browse and navigate the wiki locally
- the UI is helpful but non-essential
- agents can still operate entirely through CLI

### Planned PR slices
- `M9-P1` Local web UI browse/search shell
- `M9-P2` Planning/runs UI views

---

## Milestone 10 — Post-MVP: queue robustness and repair workflows

### Goal
Make Splendor resilient in the face of failed ingest/maintenance jobs.

### Scope
- stronger queue semantics
- retry policies
- dead-letter handling
- explicit repair commands
- better visibility into unfinished work

### Deliverables
- queue retry/backoff controls
- `splendor queue retry`
- `splendor queue inspect`
- `splendor repair ingest <source-id>`
- dead-letter item handling
- stale lease recovery

### Exit criteria
- users can recover from broken jobs without manual state surgery
- queue state is transparent and trustworthy
- repeated maintenance/ingest workflows are operationally sane

### Planned PR slices
- `M10-P1` Queue inspect/retry/repair commands
- `M10-P2` Backoff, dead-letter, and stale-lease recovery

---

## Milestone 11 — Post-MVP: richer source handling

### Goal
Expand supported source types where they materially increase product value.

### Scope
- PDF ingest
- image-based ingest
- OCR support
- richer derived artifacts
- optional model/provider integrations for harder formats

### Deliverables
- source-type dispatch architecture
- OCR pipeline hooks
- storage of OCR/parsed artifacts in `derived/`
- page updates based on extracted text
- source configuration profiles

### Important constraint
Harder source formats should remain optional. The text-native path must stay strong and simple.

### Dependency note

This milestone should build on the source-resolution refactor rather than bypass it. PDF, OCR, and
other richer source types should enter the system through the same `source_ref` plus `storage_mode`
model as text-native sources.

### Exit criteria
- PDF/image workflows exist and are clearly separated from the core text flow
- extraction artifacts are stored cleanly and repairably
- failures in OCR-heavy paths do not destabilize the core system

### Planned PR slices
- `M11-P1` Rich-source dispatch and PDF path
- `M11-P2` OCR/image ingest path

---

## Milestone 12 — v1 stabilization and release

### Goal
Publish a coherent, documented v1 that feels like a complete product.

### Scope
- contract hardening
- docs and examples
- migration notes
- versioned schemas
- extension points
- performance polish
- one or two real-world showcase repos

### Planned PR slices
- `M12-P1` Schema/docs/migration stabilization
- `M12-P2` Extension/performance/release finalization

### Deliverables
- v1 schema versions
- migration documentation for earlier repos
- end-to-end tutorials
- reference example repos
- stable CLI docs
- provider/backend docs
- GitHub optional integration docs
- roadmap for post-v1 search/index accelerators

### Exit criteria
- the product is stable enough for sustained real-world use
- the architecture is coherent
- the CLI, file contracts, and workflow model are documented and dependable
- the difference between core and optional features is very clear

---

## 4. Cross-Cutting Workstreams

These should run across multiple milestones.

## 4.1 Testing

From Milestone 1 onward:
- unit tests for schemas and commands
- fixture repos for ingest/query flows
- golden tests for generated markdown structures where possible

Later:
- integration tests with sample repos
- GitHub Actions smoke tests
- UI smoke tests

## 4.2 Documentation

Needed throughout:
- conceptual docs
- CLI docs
- schema docs
- workflow docs
- real examples

## 4.3 Prompt/agent contract quality

Since agents will likely interact with Splendor heavily:
- maintain a strong `AGENTS.md`
- keep schema docs tight
- document safe operational flows
- avoid underspecified commands

## 4.4 Provider abstraction

Keep model/provider integration modular:
- local key use
- GitHub Actions secret use
- optional future providers/backends

## 4.5 Performance and scaling

Do not overbuild early, but track:
- repo size
- page count
- ingest latency
- query latency
- lint cost

---

## 5. Recommended Initial Delivery Strategy

A practical initial sequence:

1. Milestone 0
2. Milestones 1–4 as the MVP core
3. Milestone 5 to harden and publish MVP
4. Milestones 6–8 as the first serious post-MVP wave
5. Milestones 9–11 selectively, depending on user demand
6. Milestone 12 for v1 release

## 6. Suggested Definition of MVP

Splendor should be called MVP-ready when it can do all of the following on a real repository:

- initialize the wiki structure
- add and track sources
- ingest text-native sources one at a time
- update wiki pages incrementally
- keep an index and log
- store queue and run state durably
- avoid accidental duplicate re-ingestion
- support CLI querying
- support structured planning objects
- run deterministic lint/health checks
- operate locally without GitHub

## 7. Suggested Definition of v1

Splendor should be called v1-ready when, in addition to the MVP, it has:

- stronger provenance and review-state support
- useful code awareness
- robust queue and repair workflows
- optional GitHub-native workflows
- a coherent local UI
- stable schemas, docs, and examples
- clear separation of core vs optional capabilities

## 8. Final Roadmap Summary

The right path for Splendor is to begin as a **trustworthy CLI-first knowledge compiler for code-and-research repos**, not as a large hosted LLM platform. The roadmap should favor durable file contracts, strong provenance, and predictable local workflows first. GitHub integration, richer UI, and harder-format ingestion are valuable, but should build on top of a stable core rather than substitute for one.
