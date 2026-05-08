# Splendor

[![CI](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml/badge.svg)](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/splendor-dev/splendor/graph/badge.svg)](https://codecov.io/gh/splendor-dev/splendor)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/splendor-dev/splendor/main.svg)](https://results.pre-commit.ci/latest/github/splendor-dev/splendor/main)

Splendor is a local-first, git-native knowledge workspace for code-and-research repositories. It
stores source manifests, generated source summaries, planning records, runtime state, and a local
wiki as reviewable files inside the repository, so coding agents and humans can resume work from
durable project context instead of rebuilding it from scratch.

## What Splendor Does

- Registers curated project sources and ingests them into deterministic source-summary pages.
- Tracks source freshness, queue/run state, planning records, and generated wiki maintenance.
- Answers local queries over indexed project knowledge.
- Produces agent handoffs with `brief --agent-context` and `suggest-next`.
- Keeps source discovery and source curation separate: broad scans preview by default and require
  explicit apply flags before writing manifests.
- Runs without hosted services, background workers, hosted databases, or a mandatory GitHub-only
  workflow.

## Install

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

### From A Release Wheel

Use the wheel attached to the matching GitHub Release:

```bash
TAG="v..."
VERSION="${TAG#v}"
uv tool install "https://github.com/splendor-dev/splendor/releases/download/${TAG}/splendor-${VERSION}-py3-none-any.whl"
splendor --help
```

Set `TAG` to the exact published release under evaluation. Maintainer publishing details and the
release-page fallback live in [docs/operations/release_artifacts.md](docs/operations/release_artifacts.md).

### From A Contributor Checkout

```bash
uv sync --dev
uv run splendor --help
```

To install the local package into an environment:

```bash
uv pip install .
splendor --help
```

## 5-Minute Quickstart

This flow uses one repository that contains both your project files and the Splendor workspace. If
you are running from a contributor checkout, use `uv run splendor ...` and point `--root` at the
target repository. If Splendor is installed as a command, replace `uv run splendor` with
`splendor`.

```bash
mkdir /tmp/demo-repo

uv run splendor --root /tmp/demo-repo init

cat > /tmp/demo-repo/product-note.md <<'EOF'
# Product note

Splendor keeps a durable project wiki in git.
EOF

uv run splendor --root /tmp/demo-repo add-source /tmp/demo-repo/product-note.md
uv run splendor --root /tmp/demo-repo ingest --pending --apply
uv run splendor --root /tmp/demo-repo source lookup product-note
# Use the source_id printed by source lookup in the next command.
uv run splendor --root /tmp/demo-repo task create "Publish MVP docs" --priority high --source-ref <source-id>
uv run splendor --root /tmp/demo-repo query "durable wiki"
uv run splendor --root /tmp/demo-repo brief --agent-context "continue the docs task"
uv run splendor --root /tmp/demo-repo lint
uv run splendor --root /tmp/demo-repo health
```

The repository now contains:

- `wiki/` with generated source summaries and maintained markdown knowledge pages
- `planning/` with task, milestone, decision, and question records
- `state/` with source manifests plus queue/run/query state
- `reports/` with timestamped lint and health reports

`splendor init` prints deterministic state review groups for configuration, human workspace,
source/derived state, and runtime state paths. In cold-start repositories, use those groups as the
first review checklist before committing generated state.

For a fuller walkthrough, see [docs/guides/quickstart.md](docs/guides/quickstart.md).

## Common Workflows

### Curate And Ingest Sources

```bash
splendor repo scan --class documentation
splendor add-source README.md --capture-source-commit
splendor ingest --pending
splendor ingest --pending --apply
splendor query "current roadmap"
```

`repo scan`, `ingest --pending`, `source refresh`, `source update-path`, `workspace refresh`, and
queue cleanup commands are preview-first where they can write state. Add `--apply` only after
reviewing the planned writes.

### Check A Workspace

```bash
splendor source freshness
splendor queue inspect
splendor wiki status
splendor lint
splendor health
```

### Handoff To An Agent

```bash
splendor brief --agent-context "continue the next roadmap slice"
splendor suggest-next "continue the next roadmap slice"
splendor pr-summary --since main
```

Agent handoff is intended to keep work context ahead of Splendor maintenance. Maintenance state
remains visible, but should not become the default next action for normal implementation goals.

### Browse Locally

```bash
splendor serve
```

The local web UI is read-only. Mutating web workflows are intentionally not part of the current
surface.

For a fuller command overview, see [docs/guides/cli_overview.md](docs/guides/cli_overview.md).

## Safety Model

- Core state is local and file-based.
- Source manifests are curated records, not a dump of every file found in a repository.
- Discovery commands preview candidates before registration.
- Generated source summaries, queue records, run records, derived artifacts, and reports are
  reviewable git changes.
- Mutating maintenance commands expose preview/apply behavior where practical.
- External services are optional; core CLI workflows must remain usable without them.

## Documentation

- [Documentation index](docs/README.md)
- [Quickstart](docs/guides/quickstart.md)
- [CLI overview](docs/guides/cli_overview.md)
- [Product spec](docs/splendor_product_spec.md)
- [Schema contracts](docs/schema_contracts.md)
- [Roadmap](docs/splendor_mvp_to_v1_roadmap.md)
- [CI and repo automation](docs/operations/ci_and_repo_automation.md)
- [Release artifact operations](docs/operations/release_artifacts.md)
- [v0.5.2 release notes](docs/releases/v0_5_2_release_notes.md)

Evaluation reports, design responses, and historical planning notes are kept under `docs/` for
contributors who need them, but they are not the primary path for learning the tool.

## Contributing

Use the development environment and validation commands from [AGENTS.md](AGENTS.md):

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
```

Feature and PR work should be done on a descriptive branch, keep commits scoped, and land through a
non-draft GitHub PR with labels, milestone, and a clear description.

## What Comes Next

- Previous completed PR sub-slice: `M20-P2.1`
- Current planned slice: `M20 current-work authority model from v0.5.2 hocr retries`
- Current PR sub-slice: `M20-P1.5`
- Current PR lifecycle: `branch=in-progress; main=merged`
- Next planned slice: `M20 current-work authority classifier implementation`
- Next planned PR sub-slice: `M20-P1.6`

These planning-state lines are for contributors and agents. The detailed roadmap lives in
[docs/splendor_mvp_to_v1_roadmap.md](docs/splendor_mvp_to_v1_roadmap.md).
