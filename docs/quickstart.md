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
- a pending ingest queue record and next command

For in-repo files, the current default storage mode is `none`, which means Splendor tracks the
workspace file directly instead of copying it into `raw/sources/`.
Commit provenance capture is also explicit in the manifest: `source_commit_capture: true` preserves
an explicit `--capture-source-commit` request, `false` preserves `--no-capture-source-commit`, and
`null` means future refreshes use `sources.capture_source_commit` from `splendor.yaml`.
Older manifests that predate this field still preserve positive capture intent when they already
contain a `source_commit`.

To register a batch, use a glob or direct directory scan. Both forms process files in deterministic
path order and create pending ingest jobs for newly registered sources:

```bash
uv run splendor --root /tmp/demo-repo add-source --glob "docs/*.md"
uv run splendor --root /tmp/demo-repo add-source --dir docs
```

For real repositories, prefer curated `add-source`, `--glob`, or `--dir` registration when you
already know the source set. `splendor repo scan` is safe by default: the bare command previews
candidate sources without writing manifests, wiki pages, derived artifacts, queues, runs, or
reports.

```bash
uv run splendor --root /tmp/demo-repo repo scan
uv run splendor --root /tmp/demo-repo repo scan --json
uv run splendor --root /tmp/demo-repo repo scan --class documentation --report /tmp/demo-repo/reports/repo-scan.json
```

To register candidates from a reviewed preview, apply explicitly with a class or all-class opt-in:

```bash
uv run splendor --root /tmp/demo-repo repo scan --apply --class documentation
uv run splendor --root /tmp/demo-repo repo scan --apply --all --allow-large-apply
```

`sources.include_patterns`, `sources.exclude_patterns`, and
`sources.repo_scan_default_classes` in `splendor.yaml` control candidate discovery. Patterns are
workspace-root-relative POSIX globs; exclude matches win over include matches, and class filtering
runs after include/exclude filtering. Git-ignored files, dependency directories, build outputs, and
Splendor-managed state/output directories are skipped by default.

Readable source lookup maps titles and paths back to canonical source IDs without renaming source
records or generated `wiki/sources/src-...md` pages:

```bash
uv run splendor --root /tmp/demo-repo source lookup product-note
```

Text-bearing PDFs can be registered the same way as markdown or plain-text files:

```bash
uv run splendor --root /tmp/demo-repo add-source /tmp/demo-repo/research-note.pdf
```

During ingest, Splendor extracts PDF text locally, writes the parsed text artifact under
`derived/parsed/`, links that artifact from the source manifest, and uses the extracted text for the
generated source-summary page.

Image files and image-only PDFs require explicit OCR configuration. The current lightweight local
provider is `sidecar-text`: set `sources.ocr_enabled: true`, keep
`sources.ocr_provider: sidecar-text`, and place UTF-8 sidecar text next to the resolved source file
using the configured suffix, default `.ocr.txt` (for example `diagram.png.ocr.txt`). Successful OCR
ingest writes extracted text under `derived/ocr/`, writes sidecar checksum metadata under
`derived/metadata/`, and links both artifacts from the source manifest. When OCR is not configured,
the sidecar is missing, or extraction fails, ingest reports a deterministic one-line error and
leaves text-native/PDF-text ingest behavior unchanged.

## 4. Ingest the source

Drain the pending ingest queue:

```bash
uv run splendor --root /tmp/demo-repo ingest --pending
```

`ingest --pending` also handles due failed retries and expired ingest leases. Failed jobs wait until
their persisted `next_attempt_at` backoff time, and exhausted jobs move to `dead_letter` until an
operator runs `splendor queue retry <job-id>` or `splendor repair ingest <source-id>`.

This creates:

- a source-summary page under `wiki/sources/`
- a queue record under `state/queue/`
- a run record under `state/runs/`
- updated `wiki/index.md` and `wiki/log.md`

Generated source-summary pages are reviewer-significant when they help explain a curated source,
its provenance, or synthesis follow-up. Queue and run records are deterministic operational state;
review them for broken references or surprising failures, but do not treat every timestamp-only
record as hand-authored knowledge. Explicit reports under `reports/` should be committed only when
they support the reviewed workspace update; failed or exploratory local reports can stay local.
Readable in-repo markdown/text/code summaries default to concise excerpts, while external, copied,
parsed PDF, and OCR-derived sources keep fuller extracts because the generated artifact may be the
most convenient review surface.

After ingest, use the source ID from the ingest output or look it up by readable title/path before
inspecting likely synthesis follow-up:

```bash
uv run splendor --root /tmp/demo-repo source lookup product-note
uv run splendor --root /tmp/demo-repo wiki status
# Use the source_id printed by source lookup here.
uv run splendor --root /tmp/demo-repo wiki suggest <source-id>
```

To start a maintained synthesis page without hand-writing the schema-bound frontmatter, scaffold a
topic and rebuild the index from current wiki page metadata:

```bash
uv run splendor --root /tmp/demo-repo add-topic "Preprocessing Pipeline" \
  --tags preprocessing,audio \
  --source-refs <source-id> \
  --template research-synthesis
uv run splendor --root /tmp/demo-repo wiki rebuild-index
```

`add-topic` writes `wiki/topics/<slug>.md`, validates the frontmatter contract, and refreshes
`wiki/index.md`. `wiki rebuild-index` is idempotent and reads existing wiki page frontmatter; it
does not rewrite generated source-summary pages.

When a tracked source file changes, refresh it by ID, title, or path. Refresh detects changed
content, registers the current content as a new canonical source version when needed, and queues
ingest through the same ledger used by `add-source`. It carries the manifest's
`source_commit_capture` intent forward, so a source that was explicitly opted in or out of commit
capture keeps that behavior even if the previous version had no `source_commit` value:

```bash
uv run splendor --root /tmp/demo-repo source freshness
uv run splendor --root /tmp/demo-repo source freshness --json
uv run splendor --root /tmp/demo-repo source freshness --report /tmp/demo-repo/reports/source-freshness.json
uv run splendor --root /tmp/demo-repo source refresh product-note.md
uv run splendor --root /tmp/demo-repo ingest --pending
```

`source freshness` is a safe preview. By default it writes nothing and reports unchanged, changed,
missing, historical, and unsupported source freshness states for curated sources. Workspace-backed
changed sources include manifest/current checksums and exact next commands; older source versions
for paths already covered by a current manifest are reported as historical. Non-workspace sources
are reported as unsupported for this preview. Relative `--report` paths use the current working
directory.

Refresh does not override active ingest leases or dead-letter protections; use `queue retry` or
`repair ingest` for those recovery cases.

For release verification, use `docs/v1_release_handoff.md` as the checklist. It keeps the
quickstart focused on normal operator workflow while the handoff records validation commands,
GitHub metadata expectations, issue state, and post-v1 follow-up boundaries.

For a read-only browser view over the same status and source-detail contracts:

```bash
uv run splendor --root /tmp/demo-repo serve
```

Then open `/status` or `/sources/<source-id>` on the local server.

## Release-ready review policy

For v1-style PRs, treat source-summary pages, linked manifests, derived parsed/OCR artifacts, queue
records, run records, and explicit scan/freshness/lint/health reports as reviewer-significant when
they support the workspace update under review. They are deterministic state, not hand-written
analysis. Failed or exploratory local reports do not need to be committed unless the report itself
is the artifact being reviewed.

`source refresh` currently creates a new canonical content-addressed source version when bytes
change. Stable logical source identities, source supersession fields, automated pruning, topic-ref
migration, and a one-command full workspace refresh remain planned follow-ups rather than required
v1 behavior.

## 5. Add a planning record

Planning records should link back to sources by source ID, not by raw file path.

```bash
uv run splendor --root /tmp/demo-repo task create "Publish MVP docs" --priority high --source-ref <source-id>
```

That writes a task markdown record under `planning/tasks/`.

## 6. Query the maintained workspace

```bash
uv run splendor --root /tmp/demo-repo query "durable wiki"
uv run splendor --root /tmp/demo-repo query "durable wiki" --tag architecture
uv run splendor --root /tmp/demo-repo query --source <source-id>
uv run splendor --root /tmp/demo-repo query "durable wiki" --json
uv run splendor --root /tmp/demo-repo brief --agent-context "durable wiki" --json
uv run splendor --root /tmp/demo-repo suggest-next "durable wiki" --json
```

The query command searches maintained wiki pages and planning records. Tag filters apply to wiki
frontmatter tags; source filters require a known canonical source ID and return records whose
`source_refs` include that ID. The JSON form includes active filters and is useful for agent or
script integration. `brief --agent-context` packages query matches, source refs, wiki status,
active planning records, recent runs, and ranked next actions for a new coding-agent thread.
`suggest-next` is the smaller handoff primitive when the agent needs only what to do next: it ranks
source freshness, queue work, stale or contested pages, missing synthesis follow-up, active
planning records, maintenance reports, and goal matches without mutating the workspace.

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

Queue retry behavior is configured in `splendor.yaml` under `queue.max_attempts`,
`queue.lease_ttl_seconds`, and `queue.retry_backoff_seconds`.

## Next step

If you want the wiki to live in a separate knowledge repository instead of inside the code repo,
follow [docs/companion_repo_setup.md](companion_repo_setup.md).
