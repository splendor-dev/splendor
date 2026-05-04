# M14 Source-lifecycle Re-evaluation Gate

## Context

Issue #72 reported that Splendor was promising but not yet a high-leverage coding-agent assistant.
The largest operational problem was the source-refresh lifecycle: changed workspace files produced
new content-addressed source IDs, old records and run references became hard to reason about, topic
pages could point at stale IDs, generated-state cleanup was manual, and PR reviewers had no concise
summary of which generated changes mattered.

The post-v1 M14 sequence addressed that lifecycle loop before this gate:

- `M14-P0.1` split #72 into concrete child slices.
- `M14-P1.1` added stable `source:<workspace-path>` logical IDs and aliases.
- `M14-P1.2` added `supersedes` / `superseded_by` source refresh semantics.
- `M14-P1.3` added `splendor workspace refresh --changed --ingest --rebuild-index`.
- `M14-P1.4` added `--prune-superseded` and `--update-topic-refs`.
- `M14-P2.1` added `splendor pr-summary --since main`.

This note records the internal source-lifecycle re-evaluation gate after that sequence. It is not a
new external SynthBanshee Claude report. Instead, it checks whether the concrete #72 lifecycle
complaints can now pass through the current intended Splendor command path and records what should
remain open for a later external-agent usefulness pass.

## Baseline Workflow Run

The current intended workflow was first run from `codex/m14-synthbanshee-reeval-gate`, based on
`main` at `ef78fad0a77bf90b63cc3d45f2b1ba022bae39d6`.

```bash
/Users/shaypalachy/.local/bin/uv run splendor source freshness
/Users/shaypalachy/.local/bin/uv run splendor workspace refresh --changed --ingest --rebuild-index --prune-superseded --update-topic-refs
/Users/shaypalachy/.local/bin/uv run splendor pr-summary --since main
/Users/shaypalachy/.local/bin/uv run splendor lint
/Users/shaypalachy/.local/bin/uv run splendor health
```

Observed results:

- `source freshness` reported `total=7 unchanged=7 changed=0 missing=0 unsupported=0 historical=0`.
- `workspace refresh` found no changed curated workspace-backed sources, processed zero ingest jobs,
  rebuilt `wiki/index.md`, pruned no superseded summaries, updated no topic refs, and ended with the
  same clean freshness counts.
- `pr-summary --since main` reported merge base `ef78fad0a77bf90b63cc3d45f2b1ba022bae39d6`, zero
  changed paths, no curated source/wiki/generated-state changes, and clearly labeled latest local
  lint and health reports as not tied to the current HEAD.
- `splendor lint` passed with `Checked items: 258`.
- `splendor health` passed with `Checked records: 42`.

No manual cleanup of source manifests, generated source-summary pages, run records, queue records,
or topic refs was needed.

This baseline proves that the current clean no-op path remains coherent, but it is not enough by
itself to close #72 because #72 was primarily about changed-source lifecycle behavior.

## Controlled Changed-source Exercise

To exercise the actual #72 failure mode without committing generated workspace churn into this docs
PR, a disposable clone of this branch was created under `/tmp`. In that clone, one curated
workspace-backed source was changed:

```text
raw/imports/llm-knowledge-work/karpathy-llm-wiki-pattern.md
```

The same intended command path was then run. Because that disposable clone did not have a local
`main` branch, `splendor pr-summary --since main` failed with Git's `Needed a single revision`
error. Re-running the PR summary against the available base ref, `origin/main`, succeeded. This
does not invalidate the lifecycle result, but it is a real usability caveat for branch-only clones:
agents should use a resolvable base ref such as `origin/main` when no local `main` exists.

Observed changed-source results:

- `source freshness` reported `total=7 unchanged=6 changed=1 missing=0 unsupported=0 historical=0`
  and gave the exact `source refresh` and `ingest --pending` next commands for the changed source.
- `workspace refresh --changed --ingest --rebuild-index --prune-superseded --update-topic-refs`
  registered the changed source as
  `src-29f995be0eb8d0db3c87fb4cb3612d20da2e4d0594ffd80ccc274ec1997f7b92`.
- The previous active source
  `src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac` was linked through
  `supersedes` / `superseded_by` rather than treated as a broken active source.
- The refreshed source was ingested successfully with one new queue record, one new run record, and
  one new generated source-summary page.
- The command skipped pruning the old source-summary page because it is still referenced by
  `planning/tasks/task-harden-contradiction-review-boilerplate.md`; this is the correct conservative
  behavior, not an unsafe deletion.
- `--update-topic-refs` updated maintained topic/source refs in
  `wiki/architecture/splendor-as-llm-wiki-compiler.md`, `wiki/concepts/llm-wiki-pattern.md`, and
  `wiki/topics/llm-assisted-knowledge-work.md`.
- Final freshness reported `total=8 unchanged=7 changed=0 missing=0 unsupported=0 historical=1`.
- `splendor lint` passed with `Checked items: 273`.
- `splendor health` passed with `Checked records: 46`.
- `pr-summary --since origin/main` grouped the diff into refreshed/superseded curated sources,
  generated source-summary pages, maintained wiki/topic pages, queue/run generated state, and
  reviewer notes.

The controlled exercise is the stronger evidence for the #72 lifecycle decision: it covered changed
source detection, supersession, targeted ingest, index rebuild, conservative prune behavior,
topic-ref migration, generated-state handoff, lint, and health.

## Comparison With #72

The #72 source-refresh lifecycle complaint is materially addressed by implementation and by the
controlled changed-source exercise above. Agents now have a stable logical source layer for
workspace-backed files, explicit source supersession for changed content, one obvious workspace
refresh command, conservative pruning, topic-ref migration switches, and a PR summary that
distinguishes maintained wiki changes from generated runtime/report churn.

The generated-state review policy is also clearer. `pr-summary` does not mutate state and tells the
reviewer when lint/health information comes from latest local reports rather than the current diff.
That is a meaningful improvement over reconstructing review notes from `git status`, `wiki status`,
and individual report files.

The remaining weakness is narrower than #72 and should not be hidden by this gate. For this
planning-heavy work, Splendor still did not replace direct reading of `AGENTS.md`, `.agent-plan.md`,
the README planning block, roadmap, product spec, schema contracts, automation docs, issue response
docs, and live GitHub issues. That is partly appropriate: the repository is the source of truth.
The product gap is that Splendor has no explicit authority or staleness model for living planning
documents, so agent-facing briefs cannot reliably rank current-state authority, roadmap intent,
historical external reviews, proposals, and generated summaries for a task.

## Issue Decision

This PR recommends closing #72 once maintainers accept the gate result. Its broad source-lifecycle
and PR-handoff asks have landed and were re-evaluated against both the clean no-op path and a
controlled changed-source workflow.

The remaining high-value gap is tracked as #86:
`Add planning-doc authority metadata and task-oriented agent briefs`.

If maintainers want a new independent external-agent report before closing #72, that should be
requested explicitly as a fresh validation task. It should not block the narrower #86 follow-up from
starting.

Keep the following issues separate unless a future re-evaluation directly proves one has become
urgent:

- #94: source identity review. `M14-P1.9` audits this separately and records the disposition that
  curated workspace-backed identity is materially addressed by logical IDs, supersession, freshness
  state, path repair, and topic-ref migration without changing canonical `src-...` IDs.
- #79: mutating compile/update workflow.
- #47: ingest run-duration precision.
- #37: web document-list scaling.
- #30: repo-scan registration optimization.

## Next Slice

`M14-P4.1` follows this gate with planning-document authority metadata and task-oriented agent
briefs. That work improves the handoff layer without implementing #79 or changing schema version
`1` without an explicit migration plan.
