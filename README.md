# Splendor

[![CI](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml/badge.svg)](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/splendor-dev/splendor/graph/badge.svg)](https://codecov.io/gh/splendor-dev/splendor)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/splendor-dev/splendor/main.svg)](https://results.pre-commit.ci/latest/github/splendor-dev/splendor/main)

Splendor is a local-first, git-native, schema-driven knowledge compiler for code-and-research
repositories. It keeps a durable project wiki, source manifests, runtime records, and planning
objects inside version control instead of rebuilding context from scratch on every query.

## Install

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

### Contributor setup

```bash
uv sync --dev
uv run splendor --help
```

### Local package install

Inside any Python 3.12 environment:

```bash
uv pip install .
splendor --help
```

### Built wheel install

```bash
uv build
uv pip install dist/splendor-*.whl
splendor --help
```

## 5 Minute Quickstart

This is the primary MVP flow: one repository that contains both your project files and the
Splendor workspace.

If you are running from a contributor checkout, use `uv run splendor ...` and point `--root` at the
target repository. If you installed Splendor into an environment, replace `uv run splendor` with
`splendor`; if that environment lives inside the target repo, you can drop the explicit `--root`.

```bash
mkdir /tmp/demo-repo

uv run splendor --root /tmp/demo-repo init

cat > /tmp/demo-repo/product-note.md <<'EOF'
# Product note

Splendor keeps a durable project wiki in git.
EOF

uv run splendor --root /tmp/demo-repo add-source /tmp/demo-repo/product-note.md
uv run splendor --root /tmp/demo-repo ingest --pending
uv run splendor --root /tmp/demo-repo source lookup product-note
# Use the source_id printed by source lookup in the next command.
uv run splendor --root /tmp/demo-repo task create "Publish MVP docs" --priority high --source-ref <source-id>
uv run splendor --root /tmp/demo-repo query "durable wiki"
uv run splendor --root /tmp/demo-repo lint
uv run splendor --root /tmp/demo-repo health
```

The repo now contains:

- `wiki/` with maintained markdown knowledge pages
- `planning/` with task, milestone, decision, and question records
- `state/` with source manifests plus queue/run/query state
- `reports/` with timestamped lint and health reports

For a fuller walkthrough, see [docs/quickstart.md](docs/quickstart.md).

## Example Workspace

A small runnable example lives under [examples/in-repo-workspace](examples/in-repo-workspace). It
shows the post-`init` layout plus:

- one registered and ingested source
- one planning task linked to that source by source ID
- queue and run records from the ingest

The companion-repo guidance and sample agent instructions live in
[docs/companion_repo_setup.md](docs/companion_repo_setup.md) and
[examples/companion-repo/AGENTS.md](examples/companion-repo/AGENTS.md).

## What Splendor Is

- A deterministic CLI for initializing and maintaining a repo-native knowledge workspace
- A filesystem-first system that stores wiki pages, manifests, and runtime state in git-friendly
  files
- A project-management substrate with structured milestones, tasks, decisions, and questions

## What Splendor Is Not

- A hosted service
- A full web UI product beyond the local read-only inspection shell
- A heavyweight OCR or image-ingestion platform
- A mandatory GitHub-only workflow

## Current MVP Surface

Implemented today:

- `splendor init`
- `splendor add-source <path>`, `splendor add-source --glob "pattern"`, and
  `splendor add-source --dir path`
- `splendor source list`, `splendor source lookup [query]`, `splendor source freshness`,
  `splendor source refresh <source-id|title|path>`, and
  `splendor source update-path <source-id|logical-id|title|path> <new-path>`
- `splendor workspace refresh --changed` with optional `--ingest`, `--rebuild-index`,
  `--prune-superseded`, and `--update-topic-refs`
- `splendor ingest <source-id>`, `splendor ingest --pending`, and `splendor ingest --changed`
- `splendor queue inspect [job-id]` and `splendor queue retry <job-id>`
- `splendor repair ingest <source-id>`
- `splendor materialize-source <source-id>`
- `splendor query "<question>"`, `splendor query --tag <tag>`,
  `splendor query --source <source-id|title|path>`, and `splendor query "<question>" --json`
- `splendor file-answer --from-last-query --title "..."`
- `splendor task|milestone|decision|question ...`
- `splendor repo scan`
- `splendor repo refresh`
- `splendor add-topic "Title"` with optional `--tags`, `--source-refs`, and `--template`
- `splendor wiki status`
- `splendor wiki suggest <source-id>`
- `splendor wiki compile <source-id>` as a non-mutating review-gated contract description, plus
  `splendor wiki compile <source-id> --page <page>` for diff-backed proposals and
  `--apply --proposal-hash <hash>` for explicit reviewed synthesis-page updates
- `splendor wiki rebuild-index`
- `splendor brief [goal]` and `splendor brief --agent-context [goal]`
- config-backed authority briefs for maintained planning/docs context through
  `brief --agent-context` and `suggest-next`
- `splendor serve` for a read-only local browse/search/status/planning/runtime UI
- read-only web `/status`, `/sources/<source-id>`, `/planning`, `/runs`, and `/queue` views
- `splendor lint` and `splendor health`

Not implemented yet:

- multi-page or LLM-assisted mutating `splendor wiki compile`
- heavyweight OCR/image extraction providers
- mutating web UI actions such as add-source forms

`splendor repo scan` is safe by default: it previews candidates without writing manifests or
derived state. Registration requires `repo scan --apply` plus `--class ...` or `--all`.
`splendor source freshness` is also non-mutating by default: it compares workspace-backed curated
source files to their manifest checksums, reports unchanged/changed/missing/unsupported sources,
and prints exact `source refresh`/`ingest --pending` next commands for stale paths. `--json` emits
the same preview for machine handoff, and `--report PATH` writes only an explicit freshness report.
Relative report paths use the current working directory.
`splendor workspace refresh --changed` composes that freshness view with the existing
supersession-aware refresh path for changed curated workspace-backed sources. Add `--ingest` to
ingest only queue jobs created or reused for the refreshed sources, and add `--rebuild-index` to
regenerate `wiki/index.md` after that targeted ingest succeeds. JSON output reports both initial
and final freshness counts, skipped unresolved curated sources, and failed changed-source refreshes.
Missing, unsupported, or refresh-failed active curated sources are reported as unresolved
diagnostics while valid changed sources still refresh; the command exits non-zero when those
unresolved sources remain. Add `--prune-superseded` to delete superseded generated
`wiki/sources/<source-id>.md` summaries once a current successor summary exists, while keeping
historical source manifests and run records. Add
`--update-topic-refs` to rewrite maintained wiki page `source_refs` and generated source-reference
list bullets from superseded source IDs to the active source version ID. Prune JSON reports skipped
unsafe candidates with reasons rather than deleting ambiguous state. The command does not discover
or register uncurated files or mutate maintained synthesis content beyond that explicit source-ref
migration.
`splendor source update-path <source-id|logical-id|title|path> <new-path>` is the explicit repair
path for moved active curated workspace sources. By default it requires the old workspace path to
be missing; `--force` is available for deliberate reparenting while the old file still exists. It
validates that the new path is a supported file inside the workspace, rejects targets already
curated by another active source, updates the source manifest's workspace ref and compatibility
path fields, preserves the stable logical ID and old path alias, adds the new path alias, and
reports manifest/current checksums plus next commands. Same-byte moves queue a re-ingest so
generated source-summary provenance can refresh. Changed-byte moves are
reported as partial repairs with a non-zero exit and an explicit `source refresh` next command. The
command does not discover/register uncurated files, rewrite historical run records, or mutate
maintained synthesis pages.

`splendor ingest --changed` is the narrower stale-ingest repair path for checksum-drifted curated
workspace-backed sources when old ingest queue records are already `done`. It refreshes changed
source versions through the same supersession-aware source lifecycle, ingests only those refreshed
queue jobs, reports a clean no-op when no curated source bytes changed, and reports missing active
curated sources without preventing valid changed sources from being processed. `--json` emits
initial/final freshness counts, missing-source diagnostics, refreshed source IDs, targeted ingest
outcomes, and the summary.

`splendor health` now includes deterministic remediation hints where a narrow repair command
exists. JSON, human stdout, and Markdown reports surface missing active workspace source paths with
`source update-path` / `source freshness` guidance, checksum drift with `source refresh`,
`ingest --pending`, or `ingest --changed`, and queue repair diagnostics with `queue retry` or
`repair ingest`. Unknown source provenance refs remain diagnostic-only rather than suggesting
unsafe broad rewrites.

`splendor pr-summary --since main` is a read-only PR handoff command over local git state. It uses
the merge base between `HEAD` and the base ref for PR-style diff semantics, then summarizes curated
source manifests added, refreshed, superseded, or invalid; generated source-summary pages added,
pruned, or changed; maintained wiki/topic pages changed; queue/run/report/derived generated-state
churn; and the latest local lint/health report status when report files exist. Maintenance report
status is labeled as latest local report state, not proof that this command ran validation for the
current `HEAD`. Use `--json` for agent handoff. The command does not run lint or health, write
reports, call GitHub, or mutate workspace state.

`splendor brief --agent-context [goal]` and `splendor suggest-next [goal]` also rank configured
authority documents from `splendor.yaml` plus maintained wiki pages that opt into
`authority_role` frontmatter. This lets agent handoff distinguish current authority, roadmap,
historical review, proposal, reference, and generated-summary context, with freshness marked as
current, watch, stale, or historical. Generated `source-summary` pages remain ingestion artifacts
and are excluded from maintained authority ranking.

Generated source-summary pages are deterministic ingestion artifacts. For readable in-repo
markdown/text/code sources, Splendor defaults to concise claim-bearing excerpts and path-first
display; copied, external, parsed PDF, and OCR-derived sources keep fuller extracts by default
because the generated artifact may be the clearest review surface. Queue/run records are
mechanical provenance, while explicit reports should be committed only when they support the
reviewed workspace update.

Text-bearing PDFs are supported through the ingest dispatch path. Parsed PDF text is written under
`derived/parsed/`, linked from the source manifest, and used for the generated source-summary page.
Image sources and image-only PDFs can use explicitly configured sidecar-text OCR; extracted OCR text
is written under `derived/ocr/` with sidecar checksum metadata under `derived/metadata/`, linked from
the source manifest, and kept separate from parsed PDF artifacts.

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/companion_repo_setup.md](docs/companion_repo_setup.md)
- [docs/dogfooding.md](docs/dogfooding.md)
- [docs/issue_70_design_response.md](docs/issue_70_design_response.md)
- [docs/splendor_product_spec.md](docs/splendor_product_spec.md)
- [docs/splendor_mvp_to_v1_roadmap.md](docs/splendor_mvp_to_v1_roadmap.md)
- [docs/schema_contracts.md](docs/schema_contracts.md)
- [docs/ci_and_repo_automation.md](docs/ci_and_repo_automation.md)
- [docs/v1_release_handoff.md](docs/v1_release_handoff.md)
- [docs/m14_synthbanshee_reevaluation.md](docs/m14_synthbanshee_reevaluation.md)

## What Comes Next

- Previous completed PR sub-slice: `M15-P1.3`
- Current planned slice: `v0.2.0 evaluation release tagging readiness`
- Current PR sub-slice: `v0.2.0-release-tag-prep`
- Current PR lifecycle: `branch=in-progress; main=merged`
- Next planned slice: `post-v0.2.0 SynthBanshee/Claude Code evaluation`
- Next planned PR sub-slice: `TBD after evaluation feedback`

`M5-P2` is implemented: the repository now pairs the MVP docs/example slice with
hardening work for operational edge cases, consistent one-line CLI error output, and source/wheel
install validation.

Planning notation now distinguishes parent slices such as `M7-P2` from concrete PR sub-slices such
as `M7-P2.1`. `Current PR lifecycle: branch=in-progress; main=merged` means the current sub-slice
is in progress on feature branches and is the latest merged work once observed on `main`.

`M8-P1.1` is implemented: GitHub Actions run Splendor lint on pull requests and pushes to `main`,
run Splendor health nightly, and publish generated maintenance reports as artifacts. `M8-P2.1` is
implemented: generated-change automation can propose deterministic repo-refresh output through a
reviewable PR workflow.

`M9-P1.1` is implemented: the first read-only local web UI shell can browse and search
wiki/planning markdown. `M9-P1.2` is implemented: first-run dogfood hardening added clearer
sparse-workspace UI, non-mutating query validation, more useful source summaries, and
contradiction-review noise reduction. `M9-P1.3` is implemented: knowledge-work dogfooding expanded
the wiki and filed follow-up product tasks.

`M10-P0.1` is implemented: Splendor now has CLI-first wiki status and source-impact suggestions
for the text-native maintenance loop. `M10-P0.2` is implemented: the first project briefing command
and non-mutating review-gated compile-loop contract are in place without mutating synthesis pages.
`M10-P0.3` is implemented: it smooths the visible workflow around
`add-source -> ingest -> wiki suggest -> review`, adds restrained next-action hints after query and
file-answer, improves claim-bearing query snippets, and exposes read-only web status/source-detail
views. The goal remains explicit separation: ingest creates source summaries; reviewed
compile/update workflows maintain concept, entity, topic, architecture, and glossary pages.
`M9-P2.1` is implemented: it adds read-only planning and runtime inspection pages to the local web
UI without adding mutating web actions.

`M10-P1.1` is implemented: it adds CLI-first queue inspection, failed ingest retry, and active
ingest repair. `M10-P2.1` is implemented: it adds configurable queue retry/backoff policy,
explicit dead-letter records, and stale-lease recovery.

`M11-P1.1` is implemented: it adds deterministic bulk source registration, explicit source
refresh through the existing ingest queue, and readable source lookup by title or path without
changing canonical source IDs. `M11-P2.1` is implemented: it adds CLI-first topic scaffolding,
deterministic templates, and wiki index rebuild support. `M11-P3.1` is implemented: it adds query
filters for tags/source refs and a compact agent-context handoff mode.

`M12-P1.1`, `M12-P2.1`, and `M13-P1.1` are implemented. The M13-P2 sequence responded to the
first real agent-experience report in issue #70 by redesigning repo discovery around safe
candidate reports, curated source manifests, source freshness, and higher-signal agent handoffs.

`M13-P3.1` is implemented: release-facing docs, schema notes, automation guidance, and dogfooding
guidance are reconciled with current behavior. `M13-P3.2` is the final release handoff slice: it
records the v1 validation commands, issue state, GitHub metadata expectations, known non-blockers,
and conservative post-v1 queue in [docs/v1_release_handoff.md](docs/v1_release_handoff.md).

`M13-P2.1` is a docs/planning-only reset:

- [x] record the accepted Issue #70 design response
- [x] realign the roadmap around safe discovery, curation, freshness, and agent handoff
- [x] document planned interfaces for `repo scan`, freshness, `brief --agent-context`, and
  `suggest-next`
- [x] avoid Python, schema, test, and runtime behavior changes

`M13-P2.2` makes `splendor repo scan` safe by default. Bare scan now previews candidates without
writing manifests or derived state, `--json` emits the preview, and `--report PATH` writes only an
explicit discovery report. Registration moved behind `--apply` plus `--class ...` or `--all`, with
large candidate sets refused unless `--allow-large-apply` is passed after review.

`M13-P2.3` adds `splendor source freshness`, a safe manifest-drift preview for curated sources. It
reports path-first freshness state for workspace-backed manifests, includes manifest/current
checksums, separates historical source versions from actionable stale paths, supports JSON/report
output, and does not update manifests, wiki pages, derived artifacts, queue records, run records, or
reports unless `--report PATH` is provided.

`M13-P2.4` adds a ranked handoff surface for agents. `splendor suggest-next [goal]` is read-only
and ranks deterministic next actions from source freshness, queue failures or pending ingest work,
stale/contested/review-needed pages, missing synthesis follow-up, active planning records, recent
maintenance reports, and query matches for the optional goal. `brief --agent-context` now leads
with the same suggested work before the lower-level metadata lists. Use `--json` on either command
for machine handoff.

`M13-P2.5` is implemented: source-summary pages now keep readable in-repo source summaries compact
and claim-bearing by default, while external, copied, parsed PDF, and OCR-derived sources keep
fuller extracts when the generated artifact is the practical review surface. Human-facing output
leads with source paths or refs before canonical source IDs where practical.

`M13-P3.1` is the release-hardening pass. It reconciles the release-facing docs with the current
CLI, clarifies generated-state review policy, and records the v1 readiness audit. The audit treats
issue #41's briefing and non-mutating compile contract, #42's next-action hints, #43's pending
ingest handoff, #44's query snippets, #45's web status/source detail pages, and #46's page-state
visibility as represented in current behavior. `M15-P1.1` now starts #41's deferred mutating
compile/update workflow through #79 with explicit one-page proposal/apply semantics. `M15-P1.2`
is implemented: bare compile/suggest output now includes ranked compile-target previews while
preserving the explicit apply gate. `M15-P1.3` audits #79 and records the disposition that the
desired reviewed compile/update follow-up is materially represented by the existing one-page
proposal/apply workflow, generated/maintained page separation, deterministic output, schema-bound
frontmatter validation, and focused regression coverage. The detailed disposition matrix lives in
[docs/splendor_mvp_to_v1_roadmap.md](docs/splendor_mvp_to_v1_roadmap.md#completed-disposition-m15-p13-issue-79-disposition).
Issue #79 should close with the `M15-P1.3` disposition PR unless maintainers identify a new narrow
follow-up outside the current reviewed one-page compile/apply contract.

The current release-prep PR is not an issue-backed milestone slice. It prepares the `v0.2.0`
evaluation release by updating package version metadata, adding versioned release notes, and
reframing stale v1-tagging language so the next concrete action after merge and green `main` is the
`v0.2.0` tag. The product follow-up after that tag is a fresh SynthBanshee/Claude Code evaluation
run.

`M14-P1.1` adds the first stable logical source identity layer above content-addressed source IDs:
workspace-backed manifests now persist `source:<workspace-path>` logical IDs and path aliases while
keeping `src-...` IDs as the compatibility contract.

`M14-P1.2` makes source refresh supersession-aware: changed workspace-backed sources keep their
stable logical ID, register a new content-addressed `src-...` version, and link the previous and
current versions with `supersedes` / `superseded_by`. Health treats superseded workspace source
versions as historical provenance instead of active current-byte targets.

`M14-P1.3` adds the safe workspace refresh path:
`splendor workspace refresh --changed --ingest --rebuild-index` detects changed curated
workspace-backed sources, refreshes them through the supersession-aware source lifecycle, drains
only the refreshed sources' ingest jobs, and rebuilds the wiki index.

`M14-P1.4` adds explicit superseded generated-state cleanup to workspace refresh:
`--prune-superseded` removes old generated source-summary pages only after a successor summary
exists, and `--update-topic-refs` migrates maintained wiki source references to the active
content-addressed source version while schema version `1` continues to validate `source_refs`
against source manifests. Historical manifests and run records remain valid.

`M14-P1.5` adds the explicit stale-ingest repair path for issue #93:
`splendor ingest --changed` detects checksum-drifted curated workspace-backed sources, refreshes
them into current canonical source versions, and ingests only those refreshed queue jobs even when
the previous queue item was already `done`. Missing curated sources are reported as unresolved
diagnostics while valid changed sources continue through refresh and ingest.

`M14-P1.6` makes workspace refresh continue past unrelated unresolved curated sources: missing or
unsupported active workspace-backed sources are reported as skipped diagnostics, valid changed
sources still refresh and ingest, and the command exits non-zero while unresolved source or targeted
ingest failures remain.

`M14-P1.7` adds `splendor source update-path <source-id|logical-id|title|path> <new-path>` for
intentional file moves. It updates active workspace-backed source refs, logical IDs, aliases, and
compatibility paths without broad discovery, queues same-byte repairs for re-ingest, and points
changed-byte moves to `source refresh`.

`M14-P1.8` adds health remediation hints for the concrete source lifecycle commands now available:
missing active source paths point to `source update-path` plus freshness checks, checksum drift
points to source refresh or `ingest --changed`, and queue/runtime state points to queue retry or
ingest repair.

`M14-P1.9` records the source identity review for issue #94. The disposition is that the current
M14 source-lifecycle contract materially addresses #94 for curated workspace-backed sources without
renaming canonical `src-...` manifests or changing schema version `1`: logical IDs and aliases
provide stable selectors, source refresh records content edits as superseded versions, freshness
keeps checksum state separate from identity, `source update-path` preserves the stable logical
selector while adding the new path alias for intentional moves, and workspace refresh can migrate
maintained topic refs after refreshed versions exist. Remaining work should be a specific
regression or non-workspace extension, not a broad identity redesign.

`M14-P2.1` adds the read-only PR handoff surface:
`splendor pr-summary --since main` groups merge-base changes into curated source lifecycle records,
generated source-summary pages, maintained wiki/topic edits, generated queue/run/report churn, and
latest local maintenance report status. The human output is path-first and layout-aware, and
`--json` emits the same structure for agent handoff without mutating workspace state or depending
on GitHub.

`M14-P3.1` records the internal source-lifecycle re-evaluation gate in
`docs/m14_synthbanshee_reevaluation.md`. The gate covers both the clean current state and a
controlled changed-source exercise through freshness, full workspace refresh, PR summary, lint, and
health. It is not a new external SynthBanshee report; it recommends closing #72 after maintainer
review and moves the remaining planning-doc authority / task-brief gap to #86.

`M14-P4.1` adds planning-document authority metadata and task-oriented authority briefs. Workspaces
can list maintained planning/docs files under `briefing.authority_documents` in `splendor.yaml`,
and maintained wiki pages can opt into authority ranking with frontmatter fields
`authority_role`, `authority_freshness`, and `authority_scope`. `brief --agent-context` and
`suggest-next` include ranked authority docs for the goal while keeping generated source-summary
artifacts separate from maintained authority.

`M15-P1.1` starts the post-v1 compile/update workflow from #79. Bare
`splendor wiki compile <source-id|title|path>` remains non-mutating and prints the review contract.
Adding `--page <maintained-page>` produces a deterministic proposed update from the generated
source-summary page into a single maintained topic/concept/entity/architecture/glossary page.
The proposal includes a unified diff, target/source-summary SHA-256 hashes, and a proposal hash.
Adding `--apply --proposal-hash <hash>` is the explicit operator acceptance step that writes only
that maintained page when the current target and source-summary inputs still match the reviewed
proposal. Applied output updates schema-bound frontmatter source refs/provenance links, writes a
managed `Compiled Source Evidence` section, and refuses generated source-summary pages as compile
targets.

`M15-P1.2` makes the reviewed loop easier to run end to end without broadening mutation. Bare
`splendor wiki compile <source-id|title|path>` now includes ranked maintained-page suggestions and
ready-to-run `splendor wiki compile <source-id> --page <page>` preview commands. `splendor wiki
suggest <source-id|title|path>` exposes the same compile-preview commands in text and JSON output.
JSON output also includes structured `compile_preview_args` argv tokens so agents do not have to
parse shell text. Actual writes still require the explicit one-page `--apply --proposal-hash
<hash>` gate.

`M10-P3.1` handles issue #47 as a narrow runtime-ledger bugfix. New ingest run records capture
`started_at` with sub-second precision before source resolution/dispatch work begins and preserve
`finished_at` only when the run reaches terminal success or failure. Historical run records are not
rewritten.

### v0.2.0 evaluation readiness checklist

- [x] Safe repo discovery is non-mutating by default and requires explicit apply flags.
- [x] Curated source manifests remain the durable registry instead of a broad file mirror.
- [x] Source freshness reports changed curated workspace sources without mutating state.
- [x] Agent handoff surfaces rank next actions before metadata.
- [x] Generated source-summary pages have a clear review policy and path-first display.
- [x] CLI, schema, quickstart, automation, and dogfooding docs describe the same current behavior.
- [x] Final release handoff names validation, issue state, GitHub metadata, known non-blockers,
  and the post-v1 queue.
- [x] PR-summary tooling gives reviewers a lower-noise generated-state handoff.
- [ ] `v0.2.0` package metadata, release notes, local validation, and green `main` CI are confirmed
  before tagging.
