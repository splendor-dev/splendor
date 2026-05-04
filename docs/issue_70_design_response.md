# Issue 70 Design Response

## Status

Issue #70 is the first real external agent-experience report for Splendor. It is a product signal,
not just a bug report. The accepted direction is the middle-ground redesign:

- keep Splendor local-first, file-based, and git-native
- split source discovery, source curation, and synthesis into separate workflow stages
- make broad repo discovery safe before it can create manifest or wiki churn
- focus agent-facing value on freshness, contested knowledge, planning state, and next actions

This note began as the planning contract for the M13-P2 implementation sequence. As of M13-P3.2,
the safe-discovery, freshness, handoff, path-first source-summary, and final release-handoff parts
have landed; issue #70 is closed while #72 remains open as the source-refresh lifecycle and
agent-workflow feedback loop.

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
- Mutating registration from scan requires `--apply`. This replaced the old mutating default: the
  bare command now reports preview-only behavior and prints an explicit apply command.
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

Issue #70 is closed after the scan safety, freshness, handoff, and path-first UX gaps were
substantially addressed. Residual source-refresh lifecycle and agent-workflow feedback is tracked
in issue #72.

## M13-P3 Issue Audit

- #70 is closed after the M13-P2/M13-P3.1 response for scan safety, curated curation, source
  freshness, ranked handoff, and path-first source-summary UX.
- #72 is a separate parent feedback loop for source-refresh lifecycle and agent workflow. Stable
  workspace-backed `source:<path>` aliases, `supersedes`/`superseded_by`, safe workspace refresh,
  superseded source-summary pruning, topic-ref migration, and `splendor pr-summary --since main`
  have landed. The `M14-P3.1` source-lifecycle re-evaluation records that the broad #72 lifecycle
  loop can close once maintainers accept the gate result.
- #86 tracks the narrower planning-document authority metadata and task-oriented agent brief gap
  found by the `M14-P3.1` re-evaluation; `M14-P4.1` adds the initial metadata and ranking layer.
- #41 has shipped `splendor brief [goal]`, `brief --agent-context`, and the non-mutating
  `splendor wiki compile <source-id|title|path>` contract. Mutating compile/update support is
  tracked by #79, with `M15-P1.1` starting the explicit one-page proposal/apply path.
- #42 has shipped restrained next-action hints around add-source, ingest, query/file-answer,
  briefing, and suggest-next flows.
- #43 has shipped pending ingest queue handoff for CLI-created sources, and docs now show the
  `add-source -> ingest --pending -> source lookup` path so users do not need to copy long source
  IDs for the first ingest.
- #44 has shipped claim-bearing query snippets for generated source-summary pages.
- #45 has shipped read-only web status and source-detail surfaces; mutating web actions remain out
  of scope.
- #46 has shipped clearer generated-versus-maintained page-state visibility across docs,
  status/query output, source summaries, and web/status surfaces.
- #47 remains open as an ingest/run-state timing follow-up.
- #30 and #37 remain post-v1 performance/scaling follow-ups.
