# Splendor Agent Notes

## Operating assumptions

- The repository itself is the source of truth.
- Prefer deterministic file edits and schema validation over opaque state.
- Keep GitHub workflows optional for the product runtime, but keep repository automation strong.

## Current implementation boundary

- `splendor init` and `splendor add-source` are the supported Milestone 1 commands.
- There is no ingestion worker, OCR flow, query engine, or planning-object write path yet.
- `state/manifests/sources/` is the current canonical machine-readable source registry.

## Safe workflows

1. Read `docs/splendor_product_spec.md` and `docs/splendor_mvp_to_v1_roadmap.md` before changing
   architecture.
2. Use the schema models in `src/splendor/schemas/` as the contract for new record types.
3. Keep repository layout changes aligned with `src/splendor/layout.py`.
4. Update tests and automation docs whenever the CLI surface or workflows change.
