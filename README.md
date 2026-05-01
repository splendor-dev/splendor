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
# Copy the printed src-... identifier from the command output.

uv run splendor --root /tmp/demo-repo ingest <source-id>
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
- An OCR or rich-media ingestion pipeline in the current MVP
- A mandatory GitHub-only workflow

## Current MVP Surface

Implemented today:

- `splendor init`
- `splendor add-source <path>`, `splendor add-source --glob "pattern"`, and
  `splendor add-source --dir path`
- `splendor source list`, `splendor source lookup [query]`, and
  `splendor source refresh <source-id|title|path>`
- `splendor ingest <source-id>` and `splendor ingest --pending`
- `splendor queue inspect [job-id]` and `splendor queue retry <job-id>`
- `splendor repair ingest <source-id>`
- `splendor materialize-source <source-id>`
- `splendor query "<question>"` and `splendor query "<question>" --json`
- `splendor file-answer --from-last-query --title "..."`
- `splendor task|milestone|decision|question ...`
- `splendor repo scan`
- `splendor repo refresh`
- `splendor wiki status`
- `splendor wiki suggest <source-id>`
- `splendor wiki compile <source-id>` as a non-mutating review-gated contract description
- `splendor brief [goal]`
- `splendor serve` for a read-only local browse/search/status/planning/runtime UI
- read-only web `/status`, `/sources/<source-id>`, `/planning`, `/runs`, and `/queue` views
- `splendor lint` and `splendor health`

Not implemented yet:

- mutating review-gated `splendor wiki compile`
- topic scaffolding, templates, and index rebuild
- OCR and image extraction flows
- mutating web UI actions such as add-source forms
- changed-files-driven refresh suggestions

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/companion_repo_setup.md](docs/companion_repo_setup.md)
- [docs/dogfooding.md](docs/dogfooding.md)
- [docs/splendor_product_spec.md](docs/splendor_product_spec.md)
- [docs/splendor_mvp_to_v1_roadmap.md](docs/splendor_mvp_to_v1_roadmap.md)
- [docs/schema_contracts.md](docs/schema_contracts.md)
- [docs/ci_and_repo_automation.md](docs/ci_and_repo_automation.md)

## What Comes Next

- Previous completed PR sub-slice: `M10-P2.1`
- Current planned slice: `M11-P1`
- Current PR sub-slice: `M11-P1.1`
- Current PR lifecycle: `branch=in-progress; main=merged`
- Next planned slice: `M11-P2`
- Next planned PR sub-slice: `M11-P2.1`

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

The current PR sub-slice is `M11-P1.1`, which adds deterministic bulk source registration,
explicit source refresh through the existing ingest queue, and readable source lookup by title or
path without changing canonical source IDs. After `M11-P1`, the next Milestone 11 work moves to
topic scaffolding, templates, and index rebuild.
