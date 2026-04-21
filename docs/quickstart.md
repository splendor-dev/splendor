# Splendor Quickstart

This quickstart walks through the current MVP in the primary supported mode: one repository that
contains both your normal project files and the Splendor workspace.

## 1. Install Splendor

Choose one of these supported MVP install paths.

### Contributor checkout

```bash
uv sync --dev
uv run splendor --help
```

### Local package install

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

The examples below use `uv run splendor ... --root ...` from a contributor checkout. If you
installed Splendor into an environment instead, replace `uv run splendor` with `splendor`. If that
environment lives inside the target repository, you can also drop `--root`.

## 2. Create a demo repository

```bash
mkdir /tmp/demo-repo

uv run splendor --root /tmp/demo-repo init
```

After `init`, the workspace contains:

- `wiki/` for maintained knowledge pages
- `planning/` for task, milestone, decision, and question records
- `state/` for manifests plus queue, run, and query state
- `reports/` for lint and health output
- `splendor.yaml` for layout and source policy defaults

## 3. Register a source

Create a small text-native source file in the repo:

```bash
cat > /tmp/demo-repo/product-note.md <<'EOF'
# Product note

Splendor keeps a durable project wiki in git.
EOF
```

Register it:

```bash
uv run splendor --root /tmp/demo-repo add-source /tmp/demo-repo/product-note.md
```

The command prints:

- a stable `src-...` source ID
- the manifest path under `state/manifests/sources/`
- the source ref and storage mode

For in-repo files, the current default storage mode is `none`, which means Splendor tracks the
workspace file directly instead of copying it into `raw/sources/`.

## 4. Ingest the source

Copy the `src-...` identifier from the `add-source` output, then run:

```bash
uv run splendor --root /tmp/demo-repo ingest <source-id>
```

This creates:

- a source-summary page under `wiki/sources/`
- a queue record under `state/queue/`
- a run record under `state/runs/`
- updated `wiki/index.md` and `wiki/log.md`

## 5. Add a planning record

Planning records should link back to sources by source ID, not by raw file path.

```bash
uv run splendor --root /tmp/demo-repo task create "Publish MVP docs" --priority high --source-ref <source-id>
```

That writes a task markdown record under `planning/tasks/`.

## 6. Query the maintained workspace

```bash
uv run splendor --root /tmp/demo-repo query "durable wiki"
uv run splendor --root /tmp/demo-repo query "durable wiki" --json
```

The query command searches maintained wiki pages and planning records. The JSON form is useful for
agent or script integration.

## 7. Run deterministic checks

```bash
uv run splendor --root /tmp/demo-repo lint
uv run splendor --root /tmp/demo-repo health
uv run splendor --root /tmp/demo-repo health --json
```

- `lint` validates workspace layout, wiki/planning schemas, and reference integrity
- `health` validates source storage plus queue and run consistency

Both commands write timestamped reports under `reports/`.

## 8. Inspect the committed example

The repository includes a small committed sample at
[`examples/in-repo-workspace/`](../examples/in-repo-workspace/) that shows the same flow after one
source has already been registered and ingested.

It includes:

- `splendor.yaml`
- source files in the workspace root
- one source manifest
- one source-summary page
- one planning task
- queue and run records for the ingest

## Next step

If you want the wiki to live in a separate knowledge repository instead of inside the code repo,
follow [docs/companion_repo_setup.md](companion_repo_setup.md).
