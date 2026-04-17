# Splendor

[![CI](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml/badge.svg)](https://github.com/splendor-dev/splendor/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/splendor-dev/splendor/graph/badge.svg)](https://codecov.io/gh/splendor-dev/splendor)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/splendor-dev/splendor/main.svg)](https://results.pre-commit.ci/latest/github/splendor-dev/splendor/main)

Splendor is a local-first, git-native, schema-driven knowledge compiler for code-and-research
repositories. It is designed to keep a maintained project wiki, durable provenance records, and
planning objects inside version control instead of rebuilding context from scratch on every query.

## Status

This repository is in the bootstrap phase. Milestone 0 is established and the earliest Milestone 1
surface, the first deterministic Milestone 2 ingest path, and the first Milestone 3 planning slice
are implemented:

- Python package scaffold with `src/` layout and a minimal CLI
- `splendor init` for repository layout creation
- `splendor add-source <path>` for deterministic source registration
- `splendor ingest <source-id>` for deterministic single-source ingestion into `wiki/sources/`
- `splendor task create|list`, `splendor milestone create|list`, `splendor decision create`, and
  `splendor question create` for structured planning objects under `planning/`
- Pydantic schema foundations for source, wiki, planning, queue, and run records
- unit tests, linting, coverage, pre-commit, and GitHub Actions automation

Not implemented yet:

- OCR and derived extraction workflows
- query engine
- web UI
- advanced code-aware repository scanning

## Product shape

The current design follows two repository contracts:

- immutable raw and derived artifacts under `raw/` and `derived/`
- maintained markdown knowledge and planning state under `wiki/`, `planning/`, and `state/`

The authoritative product inputs for this repository live in:

- [`docs/splendor_product_spec.md`](docs/splendor_product_spec.md)
- [`docs/splendor_mvp_to_v1_roadmap.md`](docs/splendor_mvp_to_v1_roadmap.md)

## Local development

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)

### Install

```bash
uv sync --dev
```

### Initialize the workspace

```bash
uv run splendor init
```

### Register a source

```bash
uv run splendor add-source docs/splendor_product_spec.md
```

### Ingest a registered source

```bash
uv run splendor ingest <source-id>
```

### Run checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest --cov=splendor --cov-report=term-missing --cov-report=xml
```

### Run pre-commit locally

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## What is implemented now

- `src/splendor/cli.py` exposes the CLI entrypoint
- `src/splendor/commands/init.py` creates the baseline Splendor layout safely and idempotently
- `src/splendor/commands/add_source.py` registers immutable source files and writes validated
  source manifests
- `src/splendor/commands/ingest.py` performs deterministic single-source ingestion and writes queue,
  run, and wiki updates
- `src/splendor/schemas/` defines the initial schema contracts
- `.github/workflows/` contains CI, PR context, autofix-trigger, and weekly repo-review workflows

## What comes next

`M3-P1` is now implemented: planning-object create/list commands landed as the first Milestone 3
slice. The next planned PR is `M3-P2`, which should add query CLI support plus `splendor query
--json`.

## Additional documentation

- [`docs/schema_contracts.md`](docs/schema_contracts.md)
- [`docs/ci_and_repo_automation.md`](docs/ci_and_repo_automation.md)
- [`docs/github_automation_architecture.md`](docs/github_automation_architecture.md)
