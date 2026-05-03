# Issue 70 Design Response

## Status

Issue #70 is the first real external agent-experience report for Splendor. It is a product signal,
not just a bug report. The accepted direction is the middle-ground redesign:

- keep Splendor local-first, file-based, and git-native
- split source discovery, source curation, and synthesis into separate workflow stages
- make broad repo discovery safe before it can create manifest or wiki churn
- focus agent-facing value on freshness, contested knowledge, planning state, and next actions

This note began as the planning contract for the M13-P2 implementation sequence. As of M13-P3.1,
the safe-discovery, freshness, handoff, and path-first source-summary parts have landed; the issue
remains open as the parent agent-usefulness feedback loop.

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

## Implemented Interface Direction

M13-P2 documented and implemented these contracts:

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
- `splendor.yaml` supports `sources.include_patterns` and `sources.exclude_patterns`.
- Scan candidate output includes paths, classes, labels, ignore reasons, and whether a source is
  already curated.
- M13-P2.2 updated CLI help, README/quickstart guidance, and tests around the preview default, the
  `--apply` compatibility path, JSON output, report persistence, class filters, and large-candidate
  refusal.
- `splendor source freshness` reports curated sources whose current canonical file content differs
  from the manifest checksum, prints path-first status with exact next commands, supports JSON and
  explicit report output, separates historical source versions from actionable stale paths, and does
  not mutate manifests or derived state by default.
- `brief --agent-context` leads with actual project state, stale/contested/actionable items, and
  ranked next actions before metadata.
- `splendor suggest-next [goal]` ranks work from source freshness, queue failures or pending work,
  missing synthesis, stale/contested/review-needed pages, active planning records, maintenance
  reports, and goal matches without mutating the workspace.
- Source-summary rendering defaults readable in-repo sources to concise claim-bearing excerpts,
  keeps fuller extracts for copied/external/transformed sources, and prints source paths before
  source IDs in human-facing source-summary and CLI surfaces.
- CLI guidance distinguishes reviewer-significant generated state from mechanical queue/run/report
  churn so PR authors can explain what should be reviewed rather than asking reviewers to decode
  every generated record equally.

## Roadmap Impact

M13-P2 owns the Issue #70 agent-usefulness redesign. Release finalization moved behind that work
because Splendor was not v1-ready while a reasonable agent could accidentally register thousands of
files from a broad scan.

Issue #70 remains open as the parent product-feedback issue for residual agent-usefulness feedback
after the scan safety, freshness, handoff, and path-first UX gaps were substantially addressed.

## M13-P3.1 Issue Audit

- #70 is substantially addressed for scan safety, curated curation, source freshness, ranked
  handoff, and path-first source-summary UX, but it remains open as the parent feedback loop.
- #72 is a separate parent feedback loop for source-refresh lifecycle and agent workflow. Its stable
  logical source identities, `supersedes`/`superseded_by`, full workspace refresh, pruning, and
  `pr-summary` requests remain later M13-P3 or post-v1 work.
- #41-#46 are substantially implemented through M10-P0.2, M10-P0.3, and M13-P2.5. Remaining work,
  if any, is polish, verification, or future mutating compile workflow rather than a v1 blocker.
- #47 remains open as an ingest/run-state timing follow-up.
- #30 and #37 remain post-v1 performance/scaling follow-ups.
