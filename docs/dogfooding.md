# Dogfooding Splendor

This guide describes a deterministic way to seed and inspect a Splendor workspace from the Splendor
repository itself.

## Self-bootstrap

From the repository root:

```bash
uv run splendor init
uv run splendor repo refresh
uv run splendor lint
uv run splendor health
```

`repo refresh` scans supported in-repo files, registers source manifests, and generates the
repository architecture/topic pages that make a fresh workspace useful before any manual curation.

## Curated Notes

For external references or synthesized research notes, keep the source material as local markdown
under `raw/imports/`, then register and ingest it:

```bash
uv run splendor add-source raw/imports/example-note.md
uv run splendor ingest --pending
```

Local notes should include a clear first heading and a substantive opening paragraph. Sections such
as `Core Claims`, `Design Implications`, and `Implementation Pattern` are rendered into deterministic
source-summary key facts during ingest.

Ingest currently creates deterministic source summaries and run/provenance state. The first
`M10-P0` bridge adds `splendor wiki status` and `splendor wiki suggest <source-id>` so users and
agents can identify affected concept, entity, topic, architecture, or glossary pages before
manual review. Project briefing and a future review-gated compile/update workflow remain planned.

Dogfood runs should record usability friction separately from knowledge gaps. Pay special attention
to whether each command prints the next useful command, whether long source IDs need to be copied
manually, whether query results show claim-bearing snippets, and whether the web UI exposes enough
status to understand what changed without returning to the terminal.

## Validation

Use `--no-save` for validation queries when you do not want to update
`state/queries/last-query.json`:

```bash
uv run splendor query --no-save "LLM Wiki persistent knowledge" --json
uv run splendor lint
uv run splendor health
uv run splendor serve
```

Then inspect `/browse` and `/search?q=LLM+Wiki+persistent+knowledge` in the local web UI. A sparse
workspace should show an explicit empty state with next commands instead of appearing broken.
