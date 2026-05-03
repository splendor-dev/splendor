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

`repo refresh` scans supported in-repo files without registering new source manifests by default,
then generates the repository architecture/topic pages. To seed manifests from the same reviewed
scan, opt in explicitly:

```bash
uv run splendor repo refresh --apply-scan --all --allow-large-apply
```

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

Ingest currently creates deterministic source summaries and run/provenance state. The `M10-P0`
bridge adds `splendor wiki status`, `splendor wiki suggest <source-id>`, `splendor brief [goal]`,
`splendor suggest-next [goal]`, and a non-mutating `splendor wiki compile <source-id>` contract so
users and agents can identify affected concept, entity, topic, architecture, or glossary pages and
rank immediate handoff work before manual review. Mutating compile/update workflow support remains
planned.

For readable in-repo sources, generated source-summary pages should stay compact and path-first:
Splendor renders claim-bearing excerpts by default and keeps source paths visible before source IDs.
Commit source summaries, manifests, queue/run state, and explicit reports when they are part of a
reviewed workspace update; leave failed or exploratory local reports out unless the report itself
is the artifact under review.

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

Then inspect `/browse`, `/status`, `/sources/<source-id>`, and
`/search?q=LLM+Wiki+persistent+knowledge` in the local web UI. A sparse workspace should show an
explicit empty state with next commands instead of appearing broken.

## Current Release-Hardening Notes

M13-P2 addressed the largest issue #70 dogfood failure: broad repo discovery is now a non-mutating
candidate preview unless the operator explicitly applies a reviewed class or all-class selection.
Use `source freshness`, `brief --agent-context`, and `suggest-next` before deciding whether a
workspace needs ingest, synthesis review, queue repair, or planning follow-up.

Do not expect the current workflow to provide stable logical source identities, source
supersession/pruning, one-command full workspace refresh, or PR-summary generation yet. Those are
tracked from issue #72 as later lifecycle improvements. For v1 release work, use
`docs/v1_release_handoff.md` to separate release-blocking validation from the post-v1 dogfood queue.
