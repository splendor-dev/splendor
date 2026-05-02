# Issue 70 Design Response

## Status

Issue #70 is the first real external agent-experience report for Splendor. It is a product signal,
not just a bug report. The accepted direction is the middle-ground redesign:

- keep Splendor local-first, file-based, and git-native
- split source discovery, source curation, and synthesis into separate workflow stages
- make broad repo discovery safe before it can create manifest or wiki churn
- focus agent-facing value on freshness, contested knowledge, planning state, and next actions

This note is a planning contract for the M13-P2 implementation sequence. It does not describe
current runtime behavior where noted as planned.

## What Went Wrong

`splendor repo scan` registered thousands of files in a real companion repository. The command
treated every supported file as a source, including generated YAML, tests, source files, and
configuration. That destroyed the value of the curated source set and created a diff dominated by
manifest noise.

The report also challenged the product's value proposition for agents. Agents already read files,
grep, inspect git history, and open issues quickly. Splendor is useful only when it answers
questions the source files alone do not answer:

- what knowledge is stale
- what sources contradict each other
- what review tasks are open
- what changed since the last ingest
- what the next highest-value action is
- what a new agent should know before continuing work

The current agent handoff is also too metadata-heavy. A useful brief should front-load project
state, stale or contested knowledge, open review work, and next actions before listing source and
schema details.

## Accepted Redesign

Splendor remains a durable project knowledge system, but its center of gravity shifts from
"generate a maintained wiki for everything" to "maintain an agent context/control layer over
curated project knowledge."

The design distinction is:

- **Discovery** finds candidate files and reports them without changing source manifests.
- **Curation** explicitly accepts sources into the configured source-record registry, which defaults
  to `state/manifests/sources/` and is controlled by `layout.source_records_dir`.
- **Synthesis** creates or updates maintained wiki pages only when the result adds cross-source
  value, review context, contradiction handling, or handoff value.

Source-summary pages remain useful for opaque, transformed, external, PDF, OCR, or otherwise
hard-to-read sources. For readable in-repo markdown and code, summaries should become policy-driven
rather than assumed to be the primary value.

## Planned Interface Direction

The next implementation slices should document and then implement these contracts:

- `splendor repo scan` defaults to a non-mutating candidate preview. Non-mutating means stdout
  output only by default: no source manifests, wiki pages, derived artifacts, queue records, run
  records, or reports are written.
- `repo scan --json` emits the same preview as machine-readable JSON to stdout. Persisting a
  discovery report requires an explicit output flag such as `--report PATH`, and that flag writes
  only the report, not source manifests.
- Mutating registration from scan requires `--apply`. This is an intentional safety-breaking
  change from the current mutating default: the old behavior moves behind `--apply`, and the bare
  command should clearly say that it is preview-only and print the exact apply command.
- Broad registration requires explicit class/all opt-in and should refuse huge candidate sets
  without confirmation flags.
- `repo scan` supports class filtering, such as `--class documentation`, `--class code`, and
  `--class configuration`.
- `splendor.yaml` supports planned `sources.include_patterns` and `sources.exclude_patterns`.
- Scan candidate output includes paths, classes, labels, ignore reasons, and whether a source is
  already curated.
- M13-P2.2 must update CLI help, README/quickstart guidance, and tests around the new preview
  default, the `--apply` compatibility path, JSON output, report persistence, class filters, and
  large-candidate refusal.
- A freshness workflow reports curated sources whose current canonical file content differs from
  the manifest checksum and prints exact next commands.
- `brief --agent-context` leads with actual project state, stale/contested/actionable items, and
  next actions before metadata.
- A future `suggest-next` command ranks work from open tasks, stale sources, failed jobs, missing
  synthesis, and contradictions.

## Roadmap Impact

M13-P2 now owns the Issue #70 agent-usefulness redesign. Release finalization moves behind that
work because Splendor is not v1-ready while a reasonable agent can accidentally register thousands
of files from a broad scan.

Issue #70 remains open as the parent product-feedback issue until the implementation slices
substantially address the scan safety, freshness, handoff, and path-first UX gaps.
