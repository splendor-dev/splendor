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

### Local setup

```bash
uv sync --dev
uv run splendor --help
```

## 5 Minute Quickstart

This is the primary MVP flow: one repository that contains both your project files and the
Splendor workspace.

Run the commands below from the Splendor checkout you set up in the install step, and point
`--root` at the target repository. If you want to run the commands directly from an arbitrary repo
instead, install Splendor into that repo's environment first and drop the explicit `--root`.

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
- A web UI product in the current MVP
- An OCR or rich-media ingestion pipeline in the current MVP
- A mandatory GitHub-only workflow

## Current MVP Surface

Implemented today:

- `splendor init`
- `splendor add-source <path>`
- `splendor ingest <source-id>` and `splendor ingest --pending`
- `splendor materialize-source <source-id>`
- `splendor query "<question>"` and `splendor query "<question>" --json`
- `splendor file-answer --from-last-query --title "..."`
- `splendor task|milestone|decision|question ...`
- `splendor lint` and `splendor health`

Not implemented yet:

- OCR and image extraction flows
- local web UI
- code-aware repo scan and refresh commands

## Documentation

- [docs/quickstart.md](docs/quickstart.md)
- [docs/companion_repo_setup.md](docs/companion_repo_setup.md)
- [docs/splendor_product_spec.md](docs/splendor_product_spec.md)
- [docs/splendor_mvp_to_v1_roadmap.md](docs/splendor_mvp_to_v1_roadmap.md)
- [docs/schema_contracts.md](docs/schema_contracts.md)
- [docs/ci_and_repo_automation.md](docs/ci_and_repo_automation.md)

## What Comes Next

`M5-P1` is implemented in this branch: the repository now has an MVP entrypoint README, a dedicated
quickstart, companion-repo guidance, a committed example workspace, and smoke tests that keep the
example materials aligned with the current CLI behavior.

The next planned slice is `M5-P2`, which will focus on MVP hardening: broader coverage, error
polish, packaging, and release-quality cleanup.
