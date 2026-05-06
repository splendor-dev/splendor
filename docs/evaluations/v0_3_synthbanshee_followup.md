# Splendor Agent-Context Feedback

## 1. Ideal top-5 for the M17 task

1. Issue #89 "fix(tts): #87 follow-up — close residual sp_it WER gap (0.129) toward baseline (0.056)" — opened today 07:41, the explicit successor to PR #90 that merged at 07:14.
2. PR #90 ("effective-prosody cap addresses Whisper backdoor + helium range") body + diff — the authority for what's already done.
3. CLAUDE.md ASR sanity check policy section (#87) — newly added, defines the cost discipline and acceptance criteria for ASR work.
4. docs/m17_phase_a_validation_report.md — new file in HEAD~5 range, M17 phase-A baseline numbers.
5. synthbanshee/tts/renderer.py:_apply_effective_prosody_cap + tests/unit/test_effective_prosody_cap.py — the just-landed code surface anyone iterating on prosody needs to read first.

None of those appeared in brief's top 5 (or anywhere). All five could have been derived from:
- `git log --oneline HEAD~5..`
- `gh issue list --state open --sort created`

## 2. Housekeeping priority

Lower priority, and structurally separated, not just demoted.

Render brief as:
- Goal
- Authority
- Files
- Open work
- ⸺ Splendor maintenance ⸺
- drift/queue items

A horizontal break makes the housekeeping ignorable when it's irrelevant. Pure ranking demotion (still in the same list) doesn't help — agents read top-down and stop early.

## 3. Minimum useful git-aware scope

Priority order:
- recent commit subjects (last ~20 from merge-base with main)
- merged-PR titles/bodies covering the issue refs in the task

Branch diff (`--since main`) is necessary only when on a feature branch.

Linked issues are gravy but cheap if you already have PR bodies (they reference issues in the body).

Skip "all of the above" as a v1 — start with commits + PR bodies.

## 4. Git-awareness defaults

By default.

`splendor` is invoked inside a git repo; making git context opt-in replays the same problem (the agent has to know to ask).

Provide:
- `--no-git` escape hatch
- `--since <ref>` override

Default should be:
- "since merge-base with the configured main branch"

## 5. Orphan queue cleanup

Separate command.

Suggested:
- `splendor queue clean --orphaned --apply`
- or `splendor queue prune`

`source forget` operates on registered sources; orphan queue payloads are a different scope and shoehorning them confuses the verb.

The 9 orphans found in this repo had no source manifest at all — there's nothing for `source forget` to take a selector for.

## 6. Preview/apply semantics

Strict preview-by-default everywhere.

The cognitive cost of:
- "which mutating commands preview vs. drain immediately"

is exactly the trap that hit me with `ingest --pending`.

Uniform `--apply` semantics across the whole CLI is what makes the tool agent-safe.

`--dry-run` + clearer naming is a half-measure that still requires per-command memorization.

Ship the consistency.

## 7. Reverse curated classification

Yes — always under "Curated sources changed" if the file is in the registry.

Edge case:
- file whose active canonical source has been superseded
- registry's current canonical for that path is a different `source_id`

In that case:
- classify under "Curated sources changed"
- annotate:
       - `(superseded canonical: src-NEW)`

Don't hide it; just signal the supersession state.

## 8. Missing provenance acknowledgment

Acknowledge with a concrete command.

Options:
- `update-path` writes an annotation into the manifest:
       - `provenance.path_expected_missing: true`
       - lint respects it
- OR:
       - `splendor lint --acknowledge src-XXX:provenance-missing`

Don't auto-suppress silently — that hides real diagnostics in the case where the file went missing for some other reason.

Don't downgrade to a warning — same hiding problem.

Lint output should always be a closeable to-do list.

## 9. Most important changes

The two structural changes:
- git-aware handoff
- housekeeping demotion in `brief` / `suggest-next`

Together they transform:
- `brief --agent-context`

from:
- "report on splendor's internal state"

to:
- "report on the work"

The other three:
- orphan queue
- preview/apply consistency
- reverse curated classification

are real but cleanup-tier improvements.

(a) + (b) are the changes that flip the daily-driver verdict.

## 10. Acceptance test

"I'd start with Splendor before grep/git" if:

```bash
splendor brief --agent-context "pick up M17 ASR work"
```

returns, in this order:

1. The next open issue or PR thread to work on, with link and 1-line summary.
2. Last 3–5 authoritative changes (PR titles + 1-line bodies) tagged to the task.
3. Top 3–5 files to read first (curated sources matching the goal, ranked by relevance + recency, not token similarity).
4. Open code-level TODOs / unresolved-thread refs touching those files.
5. ⸺ separator, then a 1-line state-drift footer:
   - `14 sources drifted, 1 missing, 9 orphan queue items`
   - plus a single command to investigate

If I run that against the M17 task and the top item is #89 (not "refresh AGENTS.md"), I'll switch.

Anything less and I'll keep reaching for:

* `gh issue list`
* `git log`
  first.
