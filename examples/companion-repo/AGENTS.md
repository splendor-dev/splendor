# Example Companion-Repo Agent Rules

This file is an example for a Splendor knowledge repository that lives next to a separate code
repository. It is not the governing `AGENTS.md` for the Splendor project itself.

## Workspace intent

- Treat this repository as the knowledge repo.
- Treat the neighboring code repo as an external source location.
- Run Splendor commands against this repo root.

## Suggested commands

- Install dev dependencies: `uv sync --dev`
- Initialize the workspace: `uv run splendor init`
- Register a code-repo file: `uv run splendor add-source /absolute/path/to/code-repo/README.md`
- Ingest a registered source: `uv run splendor ingest <source-id>`
- Query maintained knowledge: `uv run splendor query "..."`
- Run deterministic checks: `uv run splendor lint` and `uv run splendor health`

## Source-linking rules

- Use source IDs such as `src-...` when linking planning records back to registered sources.
- Do not use raw external file paths as planning `source_refs`.
- Expect external sources to materialize under `raw/sources/` by default in the current MVP.
