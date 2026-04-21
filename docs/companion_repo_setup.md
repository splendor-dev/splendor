# Companion Repo Setup

This is the secondary MVP workflow: keep your code in one repository and keep the Splendor wiki in
another repository that points back to the codebase as an external source location.

Use this mode when:

- you want the knowledge workspace to evolve on its own review cadence
- you do not want `wiki/`, `planning/`, `state/`, and `reports/` at the root of the code repo
- multiple code repositories may eventually feed one knowledge repository

## Recommended layout

```text
~/work/my-app/              # code repository
~/work/my-app-knowledge/    # Splendor workspace
```

Initialize the knowledge repo normally:

```bash
cd ~/work/my-app-knowledge
uv run splendor init
```

## Register a file from the code repo

Point `splendor --root` at the knowledge repository and pass the path to the code-repo file you
want to track:

```bash
uv run splendor --root ~/work/my-app-knowledge add-source ~/work/my-app/README.md
```

For sources outside the workspace root:

- `source_ref` is recorded as the external absolute path
- the default storage mode is `copy`
- Splendor materializes a stored artifact under `raw/sources/<source-id>/`

That behavior is intentional in the current MVP. External files are copied by default so the
knowledge repo retains a stable local artifact even when the source lives elsewhere.

## Ingest and maintain from the knowledge repo

Continue to target the knowledge repo as the workspace root:

```bash
uv run splendor --root ~/work/my-app-knowledge ingest <source-id>
uv run splendor --root ~/work/my-app-knowledge query "readme"
uv run splendor --root ~/work/my-app-knowledge lint
uv run splendor --root ~/work/my-app-knowledge health
```

All maintained wiki pages, manifests, queue items, run records, and reports stay in the knowledge
repo.

## Notes on source references

- Planning and wiki records should link sources by `src-...` ID once a source has been registered.
- External source paths are valid input to `add-source`, but they are not a substitute for source
  IDs in planning relationships.
- `--storage-mode none` is not supported for external files in the current MVP.

## Example agent instructions

A lightweight sample `AGENTS.md` for companion-repo usage lives at
[`examples/companion-repo/AGENTS.md`](../examples/companion-repo/AGENTS.md). It is intentionally an
example only, not a governing file for this repository.
