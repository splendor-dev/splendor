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

- Previous completed PR sub-slice: `M20-P5.3`
- Current planned slice: `M20 mutation JSON compatibility contract cleanup (#163)`
- Current PR sub-slice: `M20-P5.4`
- Current PR lifecycle: `branch=in-progress; main=merged`
- Next planned slice: `M20 next-track selection pending`
- Next planned PR sub-slice: `TBD`

`M10-P0.1`, `M10-P0.2`, `M10-P0.3`, and `M9-P2.1` are implemented. The completed M13-P2 sequence
responds to issue #70 by making source discovery safe, keeping source manifests curated, and
shifting agent-facing value toward freshness, contested knowledge, planning state, and next
actions. The lifecycle marker means the current sub-slice is in progress on feature branches and
merged once the same committed state is observed on `main`.

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

`M8-P1.1` implements the GitHub Actions lint/health integration slice with a dedicated maintenance
workflow. `M8-P2.1` implements the optional PR-centric generated-change workflow by running
deterministic repo refresh automation and opening or updating a reviewable generated-change PR.

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
- `M10-P0` Wiki status, source-impact suggestions, and project briefing bridge

### Current PR sub-slices
- `M9-P1.1` Read-only `splendor serve` browse/search shell
- `M9-P1.2` Dogfood hardening after first local web UI trial
- `M9-P1.3` Knowledge-work dogfood and wiki extension
- `M10-P0.1` Wiki status and source-impact suggestions
- `M10-P0.2` Project briefing and compile-loop contract
- `M10-P0.3` Dogfood workflow polish and web status surfaces
- `M9-P2.1` Planning/runs UI views
- `M9-P3.1` Local web UI document-list scaling

### Milestone 9 status

`M9-P1.1` implements the first local web UI shell: a foreground FastAPI-backed `splendor serve`
command with read-only browsing, markdown detail rendering, and deterministic search over existing
wiki and planning records. `M9-P1.2` follows up on the first dogfood pass with sparse-workspace
empty states, explicit special-file browse treatment, non-mutating query validation, more useful
markdown source summaries, and contradiction-review filtering for source-summary metadata
boilerplate. `M9-P1.3` adds three researched dogfood rounds, extends the wiki with tool-landscape
and agent-context synthesis, and files follow-up product tasks from the observed workflow friction.
`M10-P0.1` adds CLI-first wiki status and source-impact suggestions before deeper planning/runs UI
work. `M10-P0.2` adds project briefing and a documented, non-mutating review-gated compile-loop
contract. `M10-P0.3` polishes the visible dogfood workflow with query snippet improvements,
restrained next-action hints, and read-only web status/source-detail surfaces. `M9-P2.1` adds
read-only planning record lists plus queue and run inspection views to the same local web shell.
`M9-P3.1` keeps browse and home listing lightweight by deriving rows from paths plus cheap markdown
metadata while deferring full document parsing to detail and search. Mutating web actions and
add-source forms remain deferred to later `M9` slices.

---

## Milestone 10-P0 — Post-MVP: text-native wiki maintenance bridge

### Goal
Close the gap between ingesting a source and maintaining higher-level wiki synthesis before adding
heavier queue repair or rich-source capabilities.

### Scope
- status reporting over wiki/source/run/review state
- source-impact suggestions for concept, topic, architecture, comparison, and overview pages
- project briefing over wiki, planning, source, and recent run state
- explicit separation between source-summary generation and synthesis-page compile/update work
- dogfood workflow polish around add-source, ingest, query, and review handoff
- read-only web status and source-detail surfaces once the CLI status contract exists

### Deliverables
- `splendor wiki status`
- `splendor wiki suggest <source-id>`
- initial project briefing command or UI view
- documented contract for a future review-gated `splendor wiki compile <source-id>`
- fixed or clarified `add-source -> ingest --pending` handoff
- restrained next-action hints after major commands
- read-only web status overview and source detail pages

### Exit criteria
- users can see whether the wiki is healthy, stale, contested, or missing follow-up synthesis
- users can ask which pages a newly ingested source should affect
- agents can assemble a compact, source-backed project orientation before continuing work
- users can move through `add-source -> ingest -> wiki suggest -> review` without copying long IDs
  or guessing the next command
- query results prefer substantive claim-bearing snippets over generated metadata boilerplate
- local web browsing exposes enough source/run/page state to explain what changed
- richer source handling remains downstream of the text-native maintenance loop

### Planned PR slices
- `M10-P0.1` Wiki status and source-impact suggestions
- `M10-P0.2` Project briefing and compile-loop contract
- `M10-P0.3` Dogfood workflow polish and web status surfaces

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

### Current PR sub-slices
- `M10-P1.1` Queue inspect/retry/repair commands
- `M10-P2.1` Backoff, dead-letter, and stale-lease recovery

### Milestone 10 status

`M10-P1.1` adds CLI-first queue inspection, failed ingest retry, and active ingest repair for
recovering broken text-native ingest jobs. `M10-P2.1` completes the queue robustness milestone with
configurable retry/backoff policy, explicit dead-letter records, and stale-lease recovery.

---

## Milestone 11 — Post-MVP: agent synthesis workflow

### Goal
Make text-native Splendor workflows smoother for coding agents and human maintainers using real
project knowledge bases.

### Scope
- source lifecycle refresh and bulk registration
- readable source lookup
- topic scaffolding and index management
- query/source lookup improvements
- compact agent-context handoff surfaces

### Deliverables
- bulk source registration and explicit source refresh commands
- topic creation helpers, templates, and wiki index rebuild
- query filters for tags and source references
- agent-context output that packages relevant project state for a new coding-agent thread

### Exit criteria
- agents can register, refresh, find, and synthesize text-native project knowledge without manual
  state surgery
- topic pages and indexes stay easier to create and maintain
- field-report gaps from the SynthBanshee dogfood session are represented by planned work

### Planned PR slices
- `M11-P1` Source lifecycle, bulk registration, refresh, and readable source lookup
- `M11-P2` Topic scaffolding, templates, and index rebuild
- `M11-P3` Query/source lookup and agent-context improvements

### Current PR sub-slices
- `M11-P1.1` Source lifecycle, bulk registration, refresh, and readable source lookup
- `M11-P2.1` Topic scaffolding, templates, and index rebuild
- `M11-P3.1` Query/source lookup and agent-context improvements

### Milestone 11 status

`M11-P1.1` is implemented: it adds deterministic bulk registration through `add-source --glob`
and `add-source --dir`, explicit source refresh via the existing ingest queue, and readable source
lookup by title/path without changing canonical source IDs. `M11-P2.1` is implemented: it adds
CLI-first topic scaffolding, deterministic topic templates, and a frontmatter-driven wiki index
rebuild. `M11-P3.1` is implemented: it adds tag/source query filters and compact agent-context
handoff output before the roadmap moves to rich-source dispatch in `M12-P1`.

---

## Milestone 12 — Post-MVP: richer source handling

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

This milestone should build on the source-resolution refactor and the text-native wiki-maintenance
bridge rather than bypass either one. PDF, OCR, and other richer source types should enter the
system through the same `source_ref` plus `storage_mode` model as text-native sources, and should
feed the same source-impact and compile/update workflow used for markdown and text.

### Exit criteria
- PDF/image workflows exist and are clearly separated from the core text flow
- extraction artifacts are stored cleanly and repairably
- failures in OCR-heavy paths do not destabilize the core system

### Planned PR slices
- `M12-P1` Rich-source dispatch and PDF path
- `M12-P2` OCR/image ingest path

### Current PR sub-slices
- `M12-P1.1` Rich-source dispatch and PDF path
- `M12-P2.1` OCR/image ingest path

### Milestone 12 status

`M12-P1.1` is implemented: it introduced source-type dispatch for ingestion and routes
text-bearing PDFs through deterministic local extraction. Parsed PDF text is stored under
`derived/parsed/`, linked from source manifests through `derived_artifacts`, and used by the same
source-summary/query path as text-native sources.

`M12-P2.1` is implemented: it adds explicitly configured image/OCR dispatch using a deterministic
sidecar-text provider. OCR-derived text is stored separately under `derived/ocr/`, linked from
source manifests through `derived_artifacts`, and used by the same generated source-summary/query
path when extraction succeeds. Sidecar checksum metadata is stored under `derived/metadata/` so
no-op ingest can detect OCR input drift. Unconfigured or unextractable OCR/image sources fail
deterministically without destabilizing text-native or text-bearing PDF ingest.

---

## Milestone 13 — v1 stabilization, agent usefulness, and release

### Goal
Publish a coherent v1 only after the first real agent-experience feedback is addressed: broad repo
discovery must be safe, source manifests must stay curated, and agent handoffs must summarize
freshness, contested knowledge, planning state, and next actions rather than mostly metadata.

### Scope
- contract hardening
- docs and examples
- migration notes
- versioned schemas
- issue #70 design response
- safe repo discovery and curation controls
- source freshness and manifest-drift reporting
- higher-signal agent handoff and next-action guidance
- source-summary policy and path-first UX
- release finalization after the redesign lands

### Planned PR slices
- `M13-P1` Schema/docs/migration stabilization
- `M13-P2` Issue #70 agent-usefulness redesign
- `M13-P3` Extension/performance/release finalization

### Current PR sub-slices
- `M13-P2.1` Docs-only design reset and roadmap realignment
- `M13-P2.2` Safe repo scan candidate discovery
- `M13-P2.3` Source freshness / manifest-drift workflow
- `M13-P2.4` Agent handoff brief and suggest-next
- `M13-P2.5` Source-summary policy and path-first UX
- `M13-P3.1` Release hardening and v1 readiness
- `M13-P3.2` Final release checklist and post-v1 handoff
- `M13-P3.3` Repo-scan registration overhead

### Deliverables
- v1 schema versions
- migration documentation for earlier repos
- issue #70 design response
- safe repo scan candidate reports
- curated source registration guidance
- freshness reporting for changed curated sources
- actionable agent handoff and next-action surfaces
- end-to-end tutorials
- reference example repos
- stable CLI docs
- provider/backend docs
- GitHub optional integration docs
- roadmap for post-v1 search/index accelerators

`M13-P2.4` is implemented: `brief --agent-context` now leads with ranked suggested work, and
`splendor suggest-next [goal]` exposes the same deterministic action model directly. Suggestions
are read-only and draw from source freshness, queue failures or pending work,
stale/contested/review-needed pages, missing synthesis follow-up, active planning records, recent
maintenance reports, and optional goal matches.

`M13-P2.5` is implemented: generated source-summary pages stay deterministic while readable
in-repo markdown/text/code sources default to concise, claim-bearing excerpts. Human CLI surfaces
lead with source paths or source refs before canonical source IDs where practical, while persisted
frontmatter, manifests, and run records continue to use canonical IDs for compatibility.

`M13-P3.1` is the release-hardening and v1 readiness audit. It keeps the implementation surface
stable, reconciles README, quickstart, schema/product docs, roadmap, CI/GitHub automation docs, and
dogfooding guidance with the current product, and records per-issue status for the open feedback
threads. Later M14 slices added stable logical source identities, supersedes/superseded_by source
semantics, safe workspace refresh, pruning, topic-ref migration, and PR-summary tooling without
adding SQLite, vector search, background workers, mutating web UI, or broad refresh discovery.

`M13-P3.2` is the final release checklist and historical post-v1 handoff. It keeps runtime
behavior stable and adds the concise release handoff in `docs/releases/v1_release_handoff.md`. Its original
post-v1 queue was later worked through by the M14/M15 follow-ups: #72 covered source lifecycle and
agent workflow work, #79 covered the deferred mutating compile/update path from #41, #47 was
targeted by `M10-P3.1`, and #30/#37 were dispositioned independently.

`M13-P3.3` handles issue #30 as a focused repo-scan apply performance/refactor slice. It preserves
safe non-mutating scan previews, explicit apply gates, source IDs, manifest validation, and queue
handoff behavior while avoiding repeated config loading and layout resolution during bulk
registration.

### M13-P3 / v0.2.0 evaluation release-readiness checklist

- [x] M13-P2 safe discovery, source freshness, agent handoff, and path-first source-summary UX have
  landed.
- [x] Release-facing docs distinguish generated source-summary artifacts from maintained synthesis
  pages and explain which generated state is reviewer-significant.
- [x] The quickstart demonstrates the queue-backed `add-source -> ingest --pending -> lookup`
  loop instead of requiring users to copy long IDs for the first ingest.
- [x] Issue #70 is closed after the M13-P2/M13-P3.1 response for agent usefulness; the later M14
  and M15 follow-ups worked through the remaining source-lifecycle, agent-brief, timing, scaling,
  identity, and compile/update issue queue.
- [x] The former #72 source-refresh lifecycle feedback loop is closed or dispositioned: stable
  logical source identities, source supersession, safe workspace refresh, superseded summary
  pruning, topic-ref migration, and `splendor pr-summary --since main` have landed.
- [x] The former #79 mutating compile/update follow-up from #41 is dispositioned by the reviewed
  one-page proposal/apply workflow, compile-target suggestions, schema-bound validation, and
  generated/maintained page separation.
- [x] Final release handoff records validation commands, docs state, issue state, GitHub metadata,
  known non-blockers, and the post-v1 queue.
- [x] No GitHub issues remained open after the M15 disposition pass and before the post-`v0.2.0`
  evaluation reopened the roadmap with M16/M17/M18 follow-ups.
- [x] The `v0.2.0` tag was published from green `main` after PR #107, and the follow-up
  SynthBanshee/Claude Code evaluation was captured as the input for the v0.3 roadmap.

### Exit criteria
- the product is stable enough for sustained real-world use
- the architecture is coherent
- the CLI, file contracts, and workflow model are documented and dependable
- broad discovery cannot accidentally create large manifest/wiki churn
- generated artifacts add value beyond readable source files
- the difference between core and optional features is very clear

## Candidate Milestone 14 — Post-v1 source lifecycle and agent workflow

### Goal
Turn the #72 feedback loop into small source-lifecycle and agent-workflow improvements without
breaking the v1 file contracts.

### Scope
- stable logical source identity design
- source supersession semantics
- full workspace refresh workflow
- superseded generated-state pruning and topic-ref migration
- PR-oriented summary output
- planning-doc authority and staleness metadata

### Candidate PR slices
- `M14-P0` Post-v1 planning intake
- `M14-P1` Source lifecycle design
- `M14-P2` PR summary and generated-state review handoff
- `M14-P3` Source-lifecycle re-evaluation gate
- `M14-P4` Planning-doc authority and task-oriented agent briefs

### Candidate PR sub-slices
- `M14-P0.1` Split #72 into child issues and assign release metadata
- `M14-P1.1` Stable logical source identities
- `M14-P1.2` Supersession-aware source refresh
- `M14-P1.3` Safe workspace refresh path
- `M14-P1.4` Superseded-state pruning and topic-ref migration
- `M14-P1.5` Stale-source ingestion for checksum-drifted curated sources
- `M14-P1.6` Repo refresh missing/broken source tolerance
- `M14-P1.7` Source path repair commands
- `M14-P1.8` Health remediation hints
- `M14-P1.9` Source identity design review
- `M14-P2.1` PR summary and lower-noise generated-state review handoff
- `M14-P3.1` Source-lifecycle re-evaluation gate
- `M14-P4.1` Planning-doc authority and task-oriented agent briefs

### Source-lifecycle re-evaluation gate

The original #72 SynthBanshee report should not be treated as resolved until the post-#72 lifecycle
loop is substantially implemented and re-evaluated. The intended sequence before that gate is:

1. `M14-P0.1` splits #72 into child issues and assigns release metadata.
2. `M14-P1.1` adds stable logical source identities while preserving content-addressed IDs for
   compatibility. The first implementation persists `source:<workspace-path>` logical IDs and
   aliases for workspace-backed source manifests without changing `src-...` manifest IDs,
   generated source-summary page IDs, queue IDs, or run provenance.
3. `M14-P1.2` makes source refresh supersession-aware, so changed sources do not leave stale runs
   or health failures for agents to clean manually before later topic-ref migration.
4. `M14-P1.3` provides one safe workspace refresh path for changed-source detection, refresh,
   ingest, index rebuild, and a health-clean end state. The first implementation is
   `splendor workspace refresh --changed --ingest --rebuild-index`, limited to curated
   workspace-backed source manifests.
5. `M14-P1.4` handles superseded generated-state pruning and topic-ref migration.
6. `M14-P1.5` adds explicit stale-source ingestion with `splendor ingest --changed`, so
   checksum-drifted curated sources can be refreshed and ingested even when previous queue jobs are
   already `done`.
7. `M14-P1.6` makes repo/workspace refresh tolerate missing or broken curated sources by
   skipping them with diagnostics while continuing valid refresh work.
8. `M14-P1.7` adds explicit `splendor source update-path` repair for moved active curated
   workspace-backed source paths without broad discovery or manual manifest JSON edits.
9. `M14-P1.8` adds deterministic health remediation hints that point diagnostics at existing
   repair commands without implementing broad source-identity redesign or provenance rewriting.
10. `M14-P1.9` audits the implemented source identity behavior against #94 and records whether the
   remaining gap is narrow enough to close or retarget without changing canonical `src-...` IDs.
11. `M14-P2.1` adds `splendor pr-summary --since main`, a read-only PR-oriented summary with
   lower-noise generated-state review guidance over local git state.

After those slices land, the gate should use a comparable planning or repo-maintenance workflow and
explicitly compare against #72. If the gate is performed internally rather than by a new external
SynthBanshee run, the result must say so and must not claim to be a fresh external-agent report.
Earlier feedback should be requested only for the narrower safe-discovery, freshness, and handoff
surfaces already shipped in M13.

`M14-P2.1` keeps the command non-mutating and schema-version-1-compatible. It summarizes
merge-base curated source manifests, generated source-summary pages, maintained wiki/topic pages,
queue/run/report churn, latest local lint/health reports when available, and reviewer notes that
distinguish meaningful generated knowledge from mechanical runtime records. It respects configured
layout paths and reports malformed changed source manifests without aborting the whole handoff.
JSON output is available for agent handoff.

`M14-P3.1` records the internal source-lifecycle re-evaluation gate after the post-#72 lifecycle
sequence. The comparable workflow in `docs/evaluations/m14_synthbanshee_reevaluation.md` used source freshness,
the full workspace refresh command, `pr-summary`, `lint`, and `health` against both the clean
current state and a disposable changed-source exercise. The result: the original source-refresh
lifecycle pain from #72 is materially addressed, and this PR recommends closing #72 once
maintainers accept the gate result. The remaining agent-usefulness gap is narrower and is tracked
by #86: planning-document authority metadata and task-oriented agent briefs.

`M14-P4.1` addresses #86 without implementing #79. It adds schema-version-1-compatible authority
metadata for configured planning/docs files and optional maintained wiki frontmatter, then teaches
`brief --agent-context` and `suggest-next` to rank current authority, roadmap, historical review,
proposal, reference, and generated-summary context for a stated goal. Generated source-summary
artifacts remain separate from maintained authority ranking.

`M14-P1.5` temporarily supersedes the documented M15 follow-up because issue #93 is an open
Milestone 14 MVP source-lifecycle repair. It adds `splendor ingest --changed` as a narrow bridge
from source freshness to supersession-aware source refresh and targeted ingest. The command does
not discover uncurated files, does not drain unrelated pending jobs, and reports missing curated
sources as unresolved diagnostics while continuing valid changed-source repair work.

`M14-P1.6` addresses issue #90 by making `splendor workspace refresh --changed` use the same
partial-progress recovery posture: missing or unsupported active curated workspace sources are
reported as skipped unresolved diagnostics, per-source refresh failures are summarized without
aborting the whole command, valid changed sources still refresh, `--ingest` remains limited to
refreshed-source queue jobs, and the command exits non-zero while unresolved sources or targeted
ingest failures remain.

`M14-P1.7` addresses issue #89 with the narrow path-repair command:
`splendor source update-path <source-id|logical-id|title|path> <new-path>`. The command repairs an
active workspace-backed source manifest after an intentional file move by validating the target as a
supported in-workspace file, rejecting paths already curated by another active source, requiring the
old path to be missing unless `--force` is supplied, updating the source ref and compatibility path,
preserving the stable logical ID and old path alias, adding the new path alias, and reporting
manifest/current checksums plus next commands. Same-byte moves queue re-ingest for the existing
source ID so generated source-summary provenance can refresh; changed-byte moves return a partial
repair status and point to `source refresh`. It does not discover/register uncurated files, rewrite
historical run records, or mutate maintained synthesis pages.

`M14-P1.8` addresses issue #95 by making `splendor health` an operational repair guide for the
repair commands that now exist. Maintenance issues can carry an optional `remediation_hint` field,
rendered in JSON, human stdout, and Markdown reports. Active workspace source path failures point
to `splendor source update-path ... <new-path>` and `splendor source freshness`; checksum drift
points to `splendor source refresh ...`, `splendor ingest --pending`, or `splendor ingest
--changed`; failed/dead-letter queue shape and expired lease diagnostics point to queue retry or
ingest repair commands. Unknown source provenance refs remain diagnostic-only and explicitly avoid
inventing unsafe broad repair commands. Health resolves run source IDs against parsed source
manifest records independently from storage/content checks, so source freshness failures remain
source diagnostics rather than false unknown-source provenance diagnostics.

`M14-P1.9` addresses issue #94 as a focused identity review/disposition, not a redesign. The audit
finds the #94 expected behavior materially covered for curated workspace-backed sources by the
landed M14 sequence: `M14-P1.1` adds stable `source:<workspace-path>` logical IDs and path aliases;
`M14-P1.2` keeps content edits as content-addressed versions linked by `supersedes` /
`superseded_by`; source freshness reports checksum drift separately from identity; `M14-P1.7`
repairs intentional moves by updating active source refs and compatibility paths while preserving
the stable logical ID and old path alias; and `M14-P1.4` can migrate maintained topic refs after
refreshed successor summaries exist. Schema version `1` and canonical `src-...` manifest/page/run
provenance IDs remain the compatibility contract. Legacy workspace-backed manifests can derive
logical identity from `source_ref`, while older non-workspace copied/stored-artifact records keep
their canonical source IDs until explicitly re-curated. Any future #94 follow-up should be a
specific regression or an explicit extension beyond curated workspace-backed sources, not a
schema-breaking source-ID migration.

## Candidate Milestone 15 — Post-v1 reviewed compile/update workflow

### Goal
Turn the deferred #79 compile/update path from #41 into a small, review-gated source-to-synthesis
maintenance loop without weakening the generated-versus-maintained page boundary.

### Scope
- deterministic source-summary evidence extraction
- explicit one-page maintained synthesis update proposals
- operator-reviewed apply semantics
- schema-bound maintained-page frontmatter validation
- continued separation between generated source summaries and maintained synthesis pages

### Candidate PR slices
- `M15-P1` Reviewed compile/update loop

### Candidate PR sub-slices
- `M15-P1.1` First reviewed compile/apply loop
- `M15-P1.2` Compile/update expansion after first reviewed page apply

### M15-P1.1 first slice

`M15-P1.1` keeps bare `splendor wiki compile <source-id|title|path>` as the non-mutating contract
surface and adds a narrow reviewed implementation behind explicit page selection. Operators run
`splendor wiki compile <source-id|title|path> --page <maintained-page>` to preview a deterministic
update from the generated source-summary page into one maintained topic, concept, entity,
architecture, or glossary page. The preview reports a unified diff, target/source-summary SHA-256
hashes, and a proposal hash. The command appends a managed `Compiled Source Evidence` section,
adds the source ID to `source_refs`, records provenance links to the source and source-summary
page, and validates schema-version-1 frontmatter before reporting the proposal. It writes only
when the operator repeats the command with `--apply --proposal-hash <hash>`, and that hash must
match the current target/source-summary inputs.

The first slice intentionally does not choose multiple pages automatically, call an LLM, create a
web UI, register new sources, refresh broad workspace state, or address #47 ingest timing, #37 web
document-list scaling, or #30 repo-scan registration performance.

### M15-P1.2 compile-target discovery expansion

`M15-P1.2` connects the first reviewed compile/apply loop to existing source-impact suggestions.
Bare `splendor wiki compile <source-id|title|path>` remains non-mutating, but now includes ranked
maintained synthesis-page suggestions and ready-to-run
`splendor wiki compile <source-id> --page <page>` preview commands. `splendor wiki suggest
<source-id|title|path>` emits the same compile-preview commands for human and JSON agent handoff.
JSON suggestions include structured `compile_preview_args` alongside the rendered command string
so agents can execute the preview command without shell parsing. This slice does not add automatic
multi-page apply, LLM synthesis, web mutation, source registration changes, broad workspace
refresh, or performance/scaling work from #47, #37, or #30.

### Completed disposition: M15-P1.3 issue #79 disposition

`M15-P1.3` is a focused disposition/audit PR for issue #79. It does not add another mutating
surface. The audit records that the desired #79 follow-up is materially represented by `M15-P1.1`
and `M15-P1.2`.

| #79 requirement | Current disposition | Evidence |
| --- | --- | --- |
| Proposed diffs before mutation | `splendor wiki compile <source-id|title|path> --page <maintained-page>` returns a one-page proposal with `proposed_diff`, target/source-summary hashes, `proposal_hash`, and `proposed_markdown`; preview mode does not write the target page. | `src/splendor/commands/wiki.py` `compile_source_into_page`; `tests/test_wiki_commands.py` `test_wiki_compile_proposes_maintained_page_update_without_mutating`; `test_wiki_compile_text_proposal_prints_reviewable_diff_and_hash` |
| Explicit accept/apply semantics | The only write path is `--apply --proposal-hash <hash>`. The hash is recomputed from source ID, target path, target hash, source-summary path/hash, and proposed markdown hash so stale previews are rejected. | `src/splendor/commands/wiki.py` `_compile_proposal_hash`; `tests/test_wiki_commands.py` `test_wiki_compile_apply_updates_only_maintained_target_page`; `test_wiki_compile_apply_rejects_stale_proposal_hash`; `test_wiki_compile_apply_requires_page`; `test_wiki_compile_apply_requires_proposal_hash` |
| Deterministic output | Compile evidence is extracted deterministically from generated source-summary sections, fenced content and generated key-fact boilerplate are skipped, output includes stable hashes, and repeated accepted compiles become no-ops. | `src/splendor/commands/wiki.py` `_compile_evidence_lines`; `_render_compile_diff`; `tests/test_wiki_commands.py` `test_wiki_compile_skips_fenced_extract_contents`; `test_wiki_compile_apply_updates_only_maintained_target_page` |
| Schema-bound frontmatter validation | Compiled markdown is validated through `KnowledgePageFrontmatter` before proposal/apply output is accepted, and invalid wiki pages block compile. | `src/splendor/commands/wiki.py` `_validate_compiled_markdown`; `tests/test_wiki_commands.py` `test_wiki_compile_rejects_invalid_wiki_pages` |
| Generated source-summary versus maintained synthesis separation | Compile targets must be maintained synthesis pages (`architecture`, `concept`, `entity`, `glossary`, or `topic`); generated `source-summary` pages are rejected as targets and are only used as evidence. | `src/splendor/commands/wiki.py` `SYNTHESIS_KINDS`; `compile_source_into_page`; `tests/test_wiki_commands.py` `test_wiki_compile_rejects_generated_source_summary_target`; `test_wiki_compile_apply_updates_only_maintained_target_page` |
| Docs/tests for mutating command behavior | Product docs describe the non-mutating contract, one-page proposal, and explicit reviewed apply gate; focused wiki command tests cover preview, apply, stale hash, invalid input, generated-target rejection, and suggestion preview arguments. | `docs/splendor_product_spec.md` section 14.6; `README.md` current MVP surface; `tests/test_wiki_commands.py` compile and suggest coverage |

Remaining deliberate non-goals are automatic multi-page mutation, LLM synthesis, mutating web UI
actions, search/index redesign, source lifecycle work, and broad roadmap expansion. Unless
maintainers identify a newly scoped gap, any future compile/update follow-up should be a new narrow
issue beyond the reviewed one-page compile/apply contract.

### M10-P3.1 ingest run-duration precision

`M10-P3.1` handles issue #47 as a focused runtime-ledger correction. Ingest run records capture
`started_at` with sub-second precision before source resolution and dispatch begin, then preserve a
terminal `finished_at` only when the run succeeds or fails. The persisted run-record shape and
schema version remain unchanged, and historical run records are not rewritten.

### Boundaries
- Promote these candidates to committed roadmap slices only after the child issues and GitHub
  milestone metadata exist.
- Keep schema version `1` compatibility unless a future migration plan is explicit.
- Preserve curated source manifests as the durable registry.
- Keep #30 and #37 independent performance/scaling follow-ups unless real repository use makes
  either one urgent.

---

## Milestone 16 — v0.3 source hygiene and registry recovery

### Goal
Make Splendor safe to retry on a real external agent workflow after the post-`v0.2.0`
SynthBanshee/Claude Code evaluation. The release target is not broader product surface; it is
recoverability, source-registration hygiene, and trustworthy validation.

### Input signal
The sanitized evaluation intake lives in `docs/evaluations/v0_2_synthbanshee_evaluation.md`. A fixture archive
is preserved outside the repository in an operator-local archive. Its SHA-256 checksum is
`8b2fea5e3cd04c99d52d79398347ff7a38b41a30c410a3a1ab1985fbe63b162c`.

### Planned PR slices
- `M16-P0` Evaluation intake and roadmap decomposition.
- `M16-P1` Source hygiene and registry recovery.
- `M16-P2` Validation correctness.
- `M16-P3` Workflow polish and trial-install polish.

### Planned PR sub-slices
- `M16-P0.1` Record v0.3 evaluation intake and issue decomposition.
- `M16-P1.1` Harden repo scan ignores and `.splendorignore` (#111).
- `M16-P1.2` Add `splendor source forget` recovery command (#109).
- `M16-P1.3` Reconcile duplicate canonical source versions (#110).
- `M16-P2.1` Fix source validation health false positives (#112).
- `M16-P2.2` Align lint path checks with live source refs (#113).
- `M16-P3.1` Loosen workspace maintenance flag coupling (#121).
- `M16-P3.2` Add JSON output for pending ingest drains (#122).
- `M16-P3.3` Publish release artifacts for easier trial installs (#120).

`M16-P3.3` adds a GitHub Actions release-artifact workflow for `v*` tags, supports manual
backfill for existing tags, verifies the tag matches package metadata, builds wheel/sdist outputs,
smoke-installs the wheel, and uploads `dist/*` to the matching GitHub Release. The canonical
external trial-install path is the GitHub Release wheel documented in `docs/operations/release_artifacts.md`.
PyPI publishing remains a separate maintainer decision outside the v0.3 recovery loop.

### Minimum v0.3 retry bar
- Repo scan honors `.gitignore`, `.splendorignore`, and safe built-in ignore rules across
  documentation scans, `--all`, class-filtered scans, and apply paths.
- Operators can clean polluted registries through `source forget` without deleting manifests by
  hand.
- Duplicate active source versions for the same canonical source ref can be reconciled through a
  documented command or automatic scan reconciliation.
- Lint reads the live source model after source refresh, path repair, and supersession repair.
- Health resolves run source IDs against the manifest store without false unknown-source errors.

### Exit criteria
- `splendor lint` and `splendor health` are trustworthy diagnostics on the acceptance fixture.
- A polluted registry has a documented, tested recovery path.
- The same Claude Code evaluator can retry Splendor on SynthBanshee without manual manifest
  surgery.

## Milestone 17 — v1 public readiness

### Goal
Prepare Splendor for public v1 evaluation after v0.3 proves safe on the real SynthBanshee workflow.
This milestone is about acceptance fixtures, external evaluator ergonomics, and higher-signal agent
handoff.

### Planned PR slices
- `M17-P1.1` Create a public mock client acceptance repository (#114).
- `M17-P2.1` Expand planning authority lifecycle (#116).
- `M17-P3.1` Improve semantic ranking for agent handoff (#115).
- `M17-P4.1` Reduce contradiction-review task noise (#117).

### Public mock client guidance
`M17-P1.1` creates
[`splendor-dev/mock-client-acceptance`](https://github.com/splendor-dev/mock-client-acceptance) as
the public mock client acceptance repository. It models a realistic small CLI/data project with
human-authored specs, implementation plans, decision records, contradictory research notes, a
non-trivial commit and merged PR history, a healthy Splendor workspace on `main`, a pinned
source-refresh scenario tag, and isolated recovery fixtures for polluted registries and
renamed-source repair. The reviewed external state is pinned by the
`m17-p1.1-acceptance-main` and `m17-p1.1-source-refresh-scenario` tags, and the operator-facing
workflow is documented in
[public mock client acceptance](evaluations/public_mock_client_acceptance.md).

### Planning authority lifecycle
`M17-P2.1` implements issue #116 by expanding authority metadata without changing schema version
`1`. Configured authority documents, maintained wiki authority pages, and goal-relevant planning
decisions can now expose lifecycle state for current, reviewed, PR-linked, historical, superseded,
and archived authority. Agent handoff surfaces use that lifecycle to rank accepted/current
decisions above stale plans or older research while retaining superseded and archived documents as
explicit historical context.

### Agent handoff ranking
`M17-P3.1` implements issue #115 by adding deterministic authority-aware relevance scoring to
`brief --agent-context` and `suggest-next`. The ranking remains local-first and schema-version-1
compatible: no vector store, database, or background semantic service is introduced. Goal terms in
titles, paths, record IDs, authority scope, and configured `applies_to` metadata are weighted above
loose body overlap, while lifecycle and freshness keep current, reviewed, and PR-linked authority
above stale, superseded, archived, or token-similar historical material.

`M17-P4.1` implements issue #117 by classifying ingest-created contradiction-review tasks as
generated planning records, excluding them from default active planning handoff, and adding
intentional task workflows to list, resolve, or mute them. Contradiction evidence remains attached
to contested source-summary pages and visible through query/review-task metadata when operators ask
for it.

## Milestone 18 — v0.4 work-first agent handoff

### Goal
Make both external evaluators want to start a real agent session with Splendor before reaching for
`git log`, `gh issue list`, `rg`, and direct file reads. The `v0.3.0` SynthBanshee and hocrgen
trials show that source lifecycle safety is now materially better, but the handoff surfaces still
report too much Splendor maintenance state before they answer the work question.

### Input signal
The v0.3 evaluation and follow-up inputs live in:

- `docs/evaluations/v0_3_synthbanshee_evaluation.md`
- `docs/evaluations/v0_3_synthbanshee_followup.md`
- `docs/evaluations/v0_3_hocrgen_evaluation.md`
- `docs/evaluations/v0_3_hocrgen_followup.md`
- `docs/evaluations/v0_4_external_retry_bar.md`

### Planned PR slices
- `M18-P0` v0.3 evaluation intake and roadmap realignment.
- `M18-P1` Git-aware, work-first agent handoff.
- `M18-P2` Authority fallback and provisional uncurated docs in handoff.
- `M18-P3` Handoff reviewability and maintenance discoverability polish.

### Planned PR sub-slices
- `M18-P0.1` Record v0.3 evaluation intake and v0.4 roadmap realignment (#138).
- `M18-P1.1` Add git-aware, work-first `brief --agent-context` and `suggest-next` (#139).
- `M18-P2.1` Add inferred authority fallback and clearly labeled uncurated-doc context (#140).
- `M18-P3.1` Improve wiki review-needed discoverability and low-noise maintenance handoff (#141).

### Minimum v0.4 retry bar
- SynthBanshee: `splendor brief --agent-context "pick up M17 ASR work"` should surface the next
  open ASR issue, the recent effective-prosody PR, ASR sanity policy, validation report, and
  renderer/tests before source-refresh or queue maintenance.
- hocrgen: `splendor brief --agent-context "Resume hocrgen planning after F3a"` should surface
  `F3b`, `.agent-plan.md`, the current roadmap critical path, the modern handwritten acquisition
  policy, README/CONTRIBUTING, planning tests, and the recent F3a PR before historical outside
  reviews.
- Git context is included by default with `--no-git` and `--since <ref>` escape hatches.
- Source freshness, queue drift, review-needed pages, and missing synthesis are structurally
  separated under a Splendor maintenance section unless the goal is explicitly maintenance-focused.

### Milestone 18 status

`M18-P0.1` is implemented. `M18-P1.1` adds git-aware, work-first handoff without changing schema
version `1`: `brief --agent-context` and `suggest-next` accept `--since <ref>` and `--no-git`,
include runtime-only local git plus best-effort read-only GitHub issue/PR context, and split
agent-facing output into work context before Splendor maintenance. `M18-P2.1` adds runtime-only
inferred authority fallback and clearly labeled provisional uncurated-document context for
conventional planning, roadmap, policy, README/CONTRIBUTING, and planning-test files.
`M18-P3.1` polishes the public-readiness handoff by keeping implementation/planning goals
work-first while exposing review-needed wiki pages, missing synthesis, queue/source maintenance,
and generated contradiction-review tasks through explicit maintenance commands and notes.

## Milestone 19 — pre-v1 workflow durability after v0.4

### Goal
After v0.4 proves that handoff is useful for real agents, make the resulting workflow reviewable
and consistently safe enough for public v1.

### Candidate PR slices
- Generated-state reviewability and compact committed mode.
- Agent-safe preview/apply consistency for mutating commands.
- Orphan queue cleanup and closeable provenance-missing acknowledgements.
- Reverse curated-source classification in `pr-summary`.
- Public acceptance coverage for the SynthBanshee and hocrgen v0.4 retry bars.
- Post-v0.4 external review intake, synthesis, and M19 sequencing.
- Legacy preview/apply harmonization for older mutating maintenance/workflow commands.
- Completion-aware current-state inference for recently merged roadmap slices.
- Broader work-thread and policy-cited implementation-surface surfacing in handoff.
- Cold-start/local-state ergonomics and narrow robustness fixes for first-time repos.

### Milestone 19 status

`M19-P1.1` starts the pre-v1 durability track by adding compact committed review groups to
`splendor pr-summary --since main`. The command now separates review-first source lifecycle,
generated source-summary, and maintained wiki changes from usually mechanical queue, run, report,
query, and derived churn, with attention groups for invalid manifests, non-passing latest local
reports, and uncategorized paths. Git-aware agent handoff surfaces point reviewers back to that
compact PR summary under Splendor maintenance context only when a branch has Splendor-specific
review groups or attention diagnostics, without promoting generated maintenance state into default
planning work.

`M19-P2.1` adds a compact mutation contract to existing preview/apply and direct-write CLI
surfaces without introducing a transaction framework. Reviewed `wiki compile`, `source forget`,
`source reconcile`, `source refresh`, and `workspace refresh` JSON outputs expose deterministic
`mutation.mode`, `mutation.mutates`, `mutation.planned`, and `mutation.written` fields, and human
output labels preview-only versus apply/direct write modes so agents can tell what is safe to run
and what changed.

`M19-P3.1` closes registry and queue cleanup gaps by adding preview/apply `splendor queue clean`
paths for orphaned queue payloads, superseded source-version queues, and completed ingest jobs.
Queue inspection now exposes additive cleanup state, and agent handoff keeps these closure commands
discoverable under maintenance context without promoting generated queue cleanup above work-first
handoff.

`M19-P4.1` records the post-v0.4 external review round and realigns the remaining pre-v1 durability
work. SynthBanshee validated the M18 work-first direction and verified the M19-P3.1 queue-cleanup
closure path, but prioritized legacy preview/apply harmonization because mixed semantics make
exploratory agent sessions unsafe. hocrgen and hocrsyngen both failed the same handoff pattern:
Splendor had git/GitHub and roadmap evidence that a slice was merged, but still ranked recently
completed work above the next roadmap item. The review findings are summarized in
`docs/evaluations/v0_4_external_review_round_summary.md` and registered in
`docs/evaluations/v0_4_external_findings_register.md`.

`M19-P5.1` closes the highest-priority V04-F1 safety gap by harmonizing the legacy mutating
workflow verbs called out by external reviewers. `ingest --pending`, `source refresh`,
`source update-path`, and `workspace refresh` now preview by default, expose the shared
`mutation.mode` / `mutation.mutates` / `mutation.planned` / `mutation.written` JSON contract, and
require explicit `--apply` before draining queue jobs or writing source manifests, source-summary
pages, run records, queue records, wiki index/log state, pruning changes, or maintained topic-ref
migrations.

After `M19-P5.1` merged, SynthBanshee follow-up issues identified two generated-state correctness
gaps that should land before broader handoff inference work resumes: generated
Evidence/Contradictions excerpts can leak control bytes into markdown/YAML, and path-repaired
source manifests can keep stale `pipeline_version` provenance after ingest rewrites `last_run_id`.
These stay under the `M19-P5` family because they are immediate post-v0.4 safety follow-ups for
generated state integrity.

`M19-P6.1` is now implemented on `main`. It makes `brief --agent-context` and `suggest-next`
reconcile stale dynamic planning state with a bounded ordered roadmap sequence and recent mainline
implementation evidence, so a recently completed current slice advances to the next open roadmap
item instead of remaining the top work recommendation. Merged PR state can corroborate the
inference, but docs-only planning intake and arbitrary historical mentions do not advance current
state by themselves.

`M19-P7.1` is implemented on `main`. It broadens GitHub issue handoff from a single best open
thread to a bounded set of related open parent/sibling issues and boosts implementation/test files
explicitly named by surfaced authority docs in read-first file ranking.

`M19-P8.1` is implemented on `main`. It completed the final M19 durability pass by adding
first-run state location/review clarity and PATH-safe git lookup regression coverage before any M20
vector-search or mutating-web bets began.

The completed M19 sequence is therefore:

- `M19-P5.2` Generated text integrity and manifest provenance fixes: eliminate control-byte
  corruption from generated Evidence/Contradictions output and keep source-manifest
  `pipeline_version` provenance coherent when ingest rewrites manifests.
- `M19-P6.1` Completion-aware current-state handoff inference: reconcile stale dynamic planning
  docs against git/GitHub merge state and ordered roadmap items so completed slices lead to the
  next open slice.
- `M19-P7.1` Handoff breadth and policy-cited implementation surfacing: show multiple relevant
  open work threads and boost files/symbols named by high-authority docs.
- `M19-P8.1` Cold-start adoption and focused robustness: make first-run state location/review
  explicit and fix the PATH-safe git lookup failure seen in the hocrsyngen trial.

The v0.5 SynthBanshee integrated-use review in
`docs/evaluations/v0_5_synthbanshee_integrated_use/summary.md` accepts the M19 blocker loop as
closed. It exercised the PATH-safe git lookup fix directly, while treating the cold-start layout
changes as accepted from release notes and local implementation coverage rather than from a fresh
cold-directory retest. It leaves four bounded polish issues for later work: #160 goal-sensitive
policy-cited read-first ranking, #161 one maintenance line leaking into the work footer, #162
too-quiet no-diff human `pr-summary`, and #163 mutation JSON compatibility aliases.

## Milestone 20 — post-v1 product bets

### Goal
Start larger product bets now that the v0.5 integrated-use review accepts the M19 durability loop
as closed, while treating the v0.5.1 hocrgen/hocrsyngen retry evidence as a new M20 product-scope
handoff signal rather than a reason to reopen M19. After `M20-P1.2` and the v0.5.1 release, the
next adoption-trust slice should focus on current-work handoff ranking before mutating web review
workflows. After `M20-P2.1` and the v0.5.2 release, the second hocrgen/hocrsyngen retry shows
that current-work handoff needs one more narrow authority-model correction before richer GitHub
integration work resumes. The human operator web/wiki review adds a parallel product bet: improve
local web legibility and wiki navigation without reducing CLI-first semantics or moving state out
of local files. Remaining M19 polish issues can ride along only when they are directly relevant to
the selected M20 implementation.

### Candidate PR slices
- `M20-P0.1` Record v0.5 SynthBanshee integrated-use review intake and M20 issue disposition.
- `M20-P1.1` Add advanced semantic search or a vector index (#118).
- `M20-P1.2` Retrieval evaluation and handoff retry fixtures (#118).
- `M20-P1.3` Record v0.5.1 hocrgen/hocrsyngen retry findings and current-work handoff plan.
- `M20-P1.4` Current-work handoff ranking from planning authority (#177).
- `M20-P2.1` Explore mutating web review workflows (#119).
- `M20-P1.5` Record v0.5.2 hocrgen/hocrsyngen retry findings and define the current-work
  authority model.
- `M20-P1.6` Implement current-work authority classification and hocr retry acceptance coverage
  (#182).
- `M20-P3.1` Add richer GitHub issue, PR, review-thread, and CI integrations on top of the
  v0.4 handoff model.
- `M20-P4.0` Define the human operator cockpit and wiki navigation design/spec/architecture
  contract.
- `M20-P4.1` Implement human-first page detail layout and deterministic project identity.
- `M20-P4.2` Implement the first read-only cockpit home read model.
- `M20-P4.3` Render planning records as a human roadmap while preserving raw record access.
- `M20-P4.4` Add attention and health interpretation for review, run, queue, and planning state.
- `M20-P4.5` Add knowledge-map navigation from related pages, tags, provenance, and backlinks.
- `M20-P4.6` Render recent insights and `wiki/log.md` as a first-class local web surface.
- `M20-P5.0` Select the post-cockpit follow-up slice.
- `M20-P5.1` Remove maintenance-only `wiki suggest` guidance from the work-context action footer
  (#161).
- `M20-P5.2` Refine goal-sensitive read-first ranking so authority-cited implementation paths
  remain visible under narrow goal phrasing (#160).
- `M20-P5.3` Make no-diff `pr-summary --since <ref>` human output loud and compact (#162).
- `M20-P5.4` Clarify the canonical mutation JSON contract and legacy queue-clean aliases (#163).

`M20-P5.4` closes the v0.5 SynthBanshee mutation-JSON compatibility finding without breaking the
v0.5.x command surface. It documents and tests `mutation.{mode,mutates,planned,written}` as the
single canonical cross-verb mutation contract for `queue clean --json`, keeps `selectors` and
`actions` as supported queue-clean-specific payloads, and marks the redundant top-level
`applied`, `summary`, `written`, and `skipped` fields as deprecated v0.5.x aliases planned for
v0.6.0 removal. The regression coverage explicitly preserves the apply-mode no-op distinction:
legacy `applied` can be true while canonical `mutation.mutates` remains false.

`M20-P1.1` starts the retrieval product bet without crossing into heavyweight infrastructure. The
first slice adds deterministic runtime acronym phrase expansion to `splendor query` and the
query-backed parts of `brief --agent-context`, using a small built-in map instead of external
services, background workers, databases, or persisted vector-index state. This is a bounded recall
improvement, not a full vector-search implementation: exact lexical evidence still ranks ahead of
expansion-only matches, and broader retrieval evaluation remains part of the M20 search track.
Mutating web review workflows stay deferred to `M20-P2.1`.

`M20-P1.2` closes the first deterministic retrieval-evaluation acceptance gap with fixture-backed
regression coverage instead of new index infrastructure. The fixtures cover
hocrgen/hocrsyngen-style retry bars where exact full-phrase evidence must beat acronym-only
evidence under competition, shorthand queries must still recover full-phrase records in non-empty
corpora, query-backed agent handoff must expose that recovery, current planning authority must
outrank stale historical review material, and completed-slice evidence must advance handoff to the
next planned slice. The subsequent v0.5.1 hocrgen/hocrsyngen retry round showed that those fixtures
improved the local acceptance surface but did not yet make Splendor pass the live day-to-day
handoff bar.

`M20-P1.3` records that v0.5.1 retry evidence in
`docs/evaluations/v0_5_1_retry_findings.md` and turns it into an implementation plan without
changing runtime behavior. The key result is that hocrsyngen applied-ingest retrieval can recover
current `S7a` evidence, but `brief --agent-context` and `suggest-next` still promote merged PR
review actions above the current slice. hocrgen has the stronger failure: after `ingest --changed`
repairs stale curated sources, exact `F6f` retrieval still fails and handoff still leads with
merged PR review or historical/generated summaries. This is now a current-work handoff-ranking and
authority-priority problem, not a reason to broaden into mutating web workflows.

`M20-P1.4` implements the runtime-only current-work handoff ranking fix (#177). It extracts current
planned work from `.agent-plan.md`, README, and roadmap authority for current/next-roadmap goals;
makes `brief --agent-context` and `suggest-next` lead with that work; demotes merged PRs, recent
commits, and completed-slice evidence to predecessor context unless the user asks to review
history; and preserves open work-thread behavior when a live issue or PR is the real current work.
The implementation remains local-first and file-based: it adds no hosted service, background
worker, mandatory external API, web workflow, or persisted index state. Broad vector-search
infrastructure, cold-start state relocation, general provider-gate ranking, and mutating web review
workflows stay out of scope for this slice. The ordered M20 sequence is therefore:

- `M20-P1.1` runtime semantic expansion for deterministic query and query-backed handoff recall.
- `M20-P1.2` retrieval evaluation and handoff retry fixture closeout.
- `M20-P1.3` v0.5.1 retry evidence intake and current-work handoff planning.
- `M20-P1.4` current-work handoff ranking from planning authority (#177).
- `M20-P2.1` mutating web review workflows after the first adoption-trust handoff follow-up.
- `M20-P1.5` v0.5.2 retry evidence intake and current-work authority-model design.
- `M20-P1.6` current-work authority classification implementation (#182).
- `M20-P3.1` richer GitHub issue, PR, review-thread, and CI integrations after the authority-model
  correction.
- `M20-P4.0` human operator cockpit and wiki navigation design/spec contract.
- `M20-P4.1` human-first page detail layout and deterministic project identity.
- `M20-P4.2` first read-only cockpit home read model.
- `M20-P4.3` planning roadmap view.
- `M20-P4.4` attention and health interpretation.
- `M20-P4.5` knowledge-map navigation.
- `M20-P4.6` recent insights and log rendering.
- `M20-P5.0` post-cockpit follow-up selection.
- `M20-P5.1` work-footer maintenance action isolation.
- `M20-P5.2` goal-sensitive read-first ranking refinement.
- `M20-P5.3` no-diff pr-summary human output polish.
- `M20-P5.4` mutation JSON compatibility contract cleanup.

`M20-P2.1` is a proposal-first slice for issue #119. It keeps the current local web UI read-only
while defining the narrow first mutation paths worth implementing later: accept one reviewed
`wiki compile` proposal for a maintained page and resolve or mute generated review tasks. Source
and queue maintenance remains a later candidate after the single-page compile path proves browser
acceptance can preserve CLI-equivalent safety. Browser-side acceptance must rerun validation
against current workspace bytes, use proposal or mutation hashes plus expected input hashes, refuse
stale proposals rather than merge them, require same-origin POST-only local-intent protections, and
leave the resulting working-tree diff as the git-native review surface. The detailed proposal lives
in `docs/mutating_web_review_workflows.md`. Runtime web mutation, source or queue maintenance apply
buttons, background workers, databases, auth, hosted services, mandatory external APIs, automatic
GitHub mutation, and broad multi-page editing stay out of scope for this slice.

`M20-P1.5` follows `M20-P2.1` chronologically even though it belongs to the `M20-P1` adoption-trust
track. The v0.5.2 release packaged the `M20-P1.4` runtime handoff fix, then fresh hocrgen and
hocrsyngen retries showed a sharper product gap: Splendor can still treat old blocker prose as the
current action. This slice is docs/design only. It records the four raw hocr replies, summarizes
the findings, and defines `docs/current_work_authority_model.md`. The model says
`brief --agent-context` and `suggest-next` must classify planning evidence before ranking it:
active or unchecked `.agent-plan.md` work outranks roadmap blocker prose, blocker prose is context
rather than a slice, gated follow-ons stay behind prerequisites, and merged PRs remain predecessor
context for current-work goals. `query` remains retrieval/search, not guaranteed handoff answer
synthesis.

`M20-P1.6` (#182) implements the narrow current-work authority classification layer needed by the
captured retry cases. The runtime remains local-first and deterministic while `current_planned_work`
adds classified evidence fields for selected work, predecessor evidence, gated follow-ons,
blocker/prerequisite context, lower-priority conflicts, and reconciled selection state. The
acceptance bar stays narrow: hocrgen current-work handoff ranks `F6f2` first, keeps `F6g` gated
behind it, preserves `F1c` only as blocker/prerequisite context, suppresses merged PRs as top
actions for current-work goals, and preserves the hocrsyngen `S8b` partial pass. This slice does
not broaden into query answer synthesis, mutating web workflows, background services, databases,
mandatory external APIs, or a general agent-memory architecture.

`M20-P3.1` (#188) starts richer GitHub issue, PR, review-thread, and CI integrations with a narrow
agent-handoff payload improvement. `brief --agent-context` and `suggest-next` keep using best-effort
`gh` context only when available, but PR work-thread entries now include normalized review decision
and status-check rollup fields plus a compact summary in the existing work-thread reason. The slice
does not add hosted services, background workers, databases, auth complexity, mandatory external
APIs, mutating web workflows, broad GitHub ingestion, or query answer synthesis.

`M20-P4.0` (#190) is a docs/design-first slice for the human operator cockpit and wiki navigation track.
It records the external review feedback that the local web UI currently exposes state without
constructing human meaning, then defines the additive design contract in
`docs/human_operator_cockpit.md`. The track keeps the CLI as the deterministic operating surface,
keeps the web UI read-only first, and treats operator views as pure read models over local files.
The first implementation follow-up should be `M20-P4.1`: human-first page detail metadata demotion
plus deterministic project identity. Broader cockpit home, planning roadmap, attention/health,
knowledge-map, and recent-insight surfaces remain staged behind that contract.

`M20-P4.1` implements that first narrow runtime follow-up. It resolves deterministic local web
project identity from `wiki/index.md`, README, workspace basename, or a quiet Splendor fallback;
makes the target project primary in page chrome; renders compact human page badges above readable
markdown; and moves full parsed metadata into a collapsed technical section. The cockpit home read
model, planning roadmap lanes, attention and recent routes, backlinks, browser mutation, config
schema expansion, databases, background workers, hosted services, and external APIs remain deferred.

`M20-P4.2` (#192) implements the first cockpit home read model for `/`. The root route is now
driven by a pure request-time read model over local files and leads with project orientation,
planning-status fallback panes, knowledge-map summary, recent durable activity, and deterministic
inspect-next links before raw counts. It remains intentionally modest: no mutating web workflows,
databases, background workers, hosted services, mandatory external APIs, broad GitHub integration,
or query answer synthesis are introduced. Planning roadmap lanes, deeper attention and health
interpretation, backlinks, and recent-insight/log rendering remain staged behind this first home
read model. The next cockpit-track implementation follow-up is `M20-P4.3`.

`M20-P4.3` (#194) implements the planning roadmap view for `/planning`. The route now leads with
deterministic human-readable lanes for active/current, next, blocked or gated, open decisions, open
questions, completed/answered, and historical/archived planning records while keeping raw
kind-specific planning tables reachable for audit and debugging. The implementation stays
read-only and request-time over local planning files; it does not add mutation flows, background
jobs, databases, hosted services, broad search changes, or external APIs. Deeper attention and
health interpretation remains the next cockpit-track follow-up in `M20-P4.4`.

`M20-P4.4` (#196) adds shared read-only attention and health interpretation across the home,
status, planning, runs, and queue web routes. The implementation promotes review-needed pages,
source coverage gaps, failed or incomplete runs, queue records that need inspection, and blocked or
open planning records into human explanations with evidence references and CLI hints while keeping
the raw tables and documents available. Knowledge-map navigation from related pages, tags,
provenance, and backlinks remains the next cockpit-track follow-up in `M20-P4.5`.

`M20-P4.5` (#198) adds the first read-only knowledge-map navigation pass. `/browse` now leads with
deterministic page-role, tag, relationship, source-backed, review-needed, and orphan-page groups
before the raw document table, while document detail pages render related context from existing
related-page, tag, source, run, provenance, planning, issue/PR, contradiction, and computed backlink
inputs before technical metadata. Recent insights and `wiki/log.md` rendering remains the next
cockpit-track follow-up in `M20-P4.6`.

`M20-P4.6` (#200) makes recent durable activity a first-class read-only cockpit surface. `/recent`
renders parsed `wiki/log.md` insights, the full markdown log body, and recent run-record events
from local filesystem state while keeping raw log and run records reachable. It avoids per-user
last-seen state, filesystem mtime ordering, mutation flows, background workers, databases, hosted
services, and new persistent indexes. The `M20-P4` cockpit sequence is complete enough that the
next roadmap sub-slice should be selected explicitly rather than inferred from this track.

`M20-P5.0` (#202) is that explicit selection slice. The remaining open Milestone 20 polish issues
at this selection point (#160-#163) are all bounded, but they are not equally good as the immediate
next step. The ordering rule is to prefer the smallest fix that improves the agent handoff path
most directly. #161 wins that filter because it is a narrow bug in `brief --agent-context`: remove
the maintenance-only `splendor wiki suggest <source-id>` action from the work footer while
preserving explicit maintenance guidance where it belongs. #160 remains a broader goal-sensitive
ranking refinement, #162 is isolated no-diff `pr-summary` human-output polish, and #163 is a
queue-clean JSON compatibility-contract cleanup.

`M20-P5.1` (#161) implements the narrow work-footer maintenance isolation fix. Agent-context
briefs now build their trailing next-action footer from work actions instead of the combined
work-plus-maintenance suggestion list, and the standalone missing-synthesis `wiki suggest` footer
line is removed. Explicit maintenance context still carries `splendor wiki suggest <source-id>`
commands and wiki-maintenance notes, so operators can find the maintenance path without presenting
it as default work. The next smallest handoff-polish follow-up is `M20-P5.2`: issue #160's
goal-sensitive read-first ranking refinement.

`M20-P5.2` (#160) refines `brief --agent-context` read-first ranking after the M19-P7.1
policy-cited improvement. Authority docs can already name implementation and test files, but
goal-specific git context can still crowd those files out of the bounded read-first list. This
slice keeps the behavior deterministic by preserving a small bounded set of the highest-ranked
authority-cited paths when git and GitHub context are noisy. The next narrow polish follow-up is
`M20-P5.3`: issue #162's no-diff `pr-summary --since <ref>` human-output short-circuit.

`M20-P5.3` (#162) makes the human `pr-summary --since <ref>` path loud when there is no current
diff to review. JSON keeps its existing compact committed contract, while human output
short-circuits before empty review groups when the changed-path count is zero, including the
common `HEAD`-equals-merge-base case. The next narrow polish follow-up is `M20-P5.4`: issue
#163's mutation JSON compatibility contract cleanup for `queue clean --orphaned --json`.

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
5. Milestones 9–12 selectively, depending on user demand
6. Milestone 13 for v1 release

## 6. Suggested Definition of MVP

Splendor should be called MVP-ready when it can do all of the following on a real repository:

- initialize the wiki structure
- add and track sources
- ingest text-native sources one at a time
- create deterministic source-summary pages
- suggest or update affected synthesis pages through a reviewable maintenance path
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
- wiki status, source-impact suggestions, and project briefing
- dogfood workflow polish for add/ingest/query/review loops
- optional GitHub-native workflows
- a coherent local UI
- stable schemas, docs, and examples
- clear separation of core vs optional capabilities

## 8. Final Roadmap Summary

The right path for Splendor is to begin as a **trustworthy CLI-first knowledge compiler for code-and-research repos**, not as a large hosted LLM platform. The roadmap should favor durable file contracts, strong provenance, and predictable local workflows first. GitHub integration, richer UI, and harder-format ingestion are valuable, but should build on top of a stable core rather than substitute for one.
