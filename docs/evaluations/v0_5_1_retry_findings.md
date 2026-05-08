# Splendor v0.5.1 hocrgen / hocrsyngen Retry Findings

This document summarizes the v0.5.1 external retry round after the M20-P1 retrieval and handoff
fixture work and the v0.5.1 patch release. It is synthesis over the raw reviewer replies, not a new
planning authority.

## Source Materials

- [hocrgen retry reply](v0_5_1_hocrgen_retry_reply.md)
- [hocrgen follow-up reply](v0_5_1_hocrgen_followup_reply.md)
- [hocrsyngen retry reply](v0_5_1_hocrsyngen_retry_reply.md)
- [hocrsyngen first follow-up reply](v0_5_1_hocrsyngen_followup_reply.md)
- [hocrsyngen second follow-up reply](v0_5_1_hocrsyngen_followup_2_reply.md)

## Review Scope

The retry round asked the two reviewers who rejected v0.4.0 as a day-to-day tool to try v0.5.1
against the same class of failures:

- `hocrgen`: returning design partner, originally blocked by Splendor reselecting completed
  `F3b` work instead of inferring the next `F4c` slice.
- `hocrsyngen`: cold-start partner, originally blocked by Splendor reselecting completed `S4c`
  work instead of inferring `S4d`, plus first-run state churn.

Both upstream repositories had moved on by the time v0.5.1 was retested. Current `hocrgen` main
pointed past the historical `F4c` target to `F6f`, and current `hocrsyngen` main pointed past the
historical `S4d` target to `S7a`. That made the live retry more useful as a current-state handoff
test than as a replay of the exact v0.4 snapshot.

## Partner Verdicts

| Partner | Verdict | Positive signal | Blocking signal |
| --- | --- | --- | --- |
| hocrgen | Still not first or early tool | Stale-source repair can refresh changed curated sources | Refreshed query still misses `F6f`; handoff still leads with merged PR review |
| hocrsyngen | Still not day-to-day tool | Applied ingest lets `query` recover `S7a` evidence | Cold-start query misses `S7a`; handoff still leads with merged PR review after ingest |

## What Improved

- Applied ingest can make indexed retrieval useful in a minimal hocrsyngen setup. After
  `splendor ingest --pending --apply`, `query "S7a"` and a richer S7a query found the relevant
  `.agent-plan.md`, roadmap, and README-backed records.
- `hocrgen` stale-source repair is operational. `splendor ingest --changed` refreshed all 27
  changed curated workspace-backed sources and left the active freshness count at zero changed
  sources.
- The outputs are inspectable enough to classify failures. The reviewers could distinguish
  stale-index state, no-init cold start, applied ingest, query retrieval, handoff ranking, and
  generated-state churn.

## What Still Failed

- Handoff ranking still treats merged PRs and commits as next work. In both repositories,
  `brief --agent-context` and `suggest-next` led with completed PR review actions after the
  reviewer supplied a current handoff goal and after relevant authority documents were discoverable.
- Current planning facts are retrievable but not promoted into the actual handoff. hocrsyngen could
  retrieve `S7a` after applied ingest, but the handoff still did not say that `S7a` was the next
  work. hocrgen had the stronger failure: refreshed index state still produced no exact `F6f`
  query match.
- Historical/generated summaries remain too competitive. hocrgen provider-gate and F6f-adjacent
  queries ranked synthetic spinout amendments and review summaries above current planning authority
  and implementation evidence.
- Cold-start behavior remains too stateful for first contact. hocrsyngen no-init query missed
  `S7a`, while `init` plus ingest left several top-level generated directories and files for the
  reviewer to inspect or clean up.
- Preview/apply wording remains adoption-sensitive. The hocrsyngen follow-up accidentally ran
  `ingest --pending` without `--apply`; the output was correct, but the workflow still required an
  extra clarification round to prove whether retrieval worked after actual ingest.

## Failure Classification

### hocrgen

- **Current target:** `F6f`, not the historical `F4c`, because current `main` had advanced.
- **Stale repair:** `ingest --changed` repaired changed source manifests and ingested refreshed
  source summaries.
- **Retrieval:** failed for exact `F6f` after refresh.
- **Ranking:** richer F6f and provider-gate queries favored stale spinout/review source summaries
  above current roadmap and `.agent-plan.md` summaries.
- **Handoff:** `brief` and `suggest-next` still led with completed PRs such as F6a/F6e and older
  roadmap PRs rather than the next planned work.
- **Implementation evidence:** provider-gate implementation files such as `source_ops` were buried,
  not promoted into the top matches.

### hocrsyngen

- **Current target:** `S7a`, not the historical `S4d`, because current `main` had advanced.
- **Cold start:** no-init `brief`, `suggest-next`, and `query` missed `S7a` and led with merged PR
  review actions.
- **Applied ingest:** after `ingest --pending --apply`, query recovered `S7a` evidence from
  `.agent-plan.md`, roadmap, and README-backed source summaries.
- **Handoff:** even after applied ingest, `brief` and `suggest-next` still led with merged PRs and
  commits instead of saying that `S7a` was the next work.
- **State churn:** `init` and ingest generated top-level Splendor state that remained visible in
  `git status`, reinforcing the first-run noise concern.

## Follow-Up Implications

The v0.5.1 retry does not invalidate M20-P1.2's fixture-backed improvement work, but it shows that
the next blocker is more specific than acronym/phrase recall. The external failures are now mostly
handoff and authority-ranking failures:

1. Extract the current planned item from `.agent-plan.md`, README, and roadmap conventions as a
   first-class handoff candidate.
2. Demote merged PRs, recent commits, and completed-slice evidence to predecessor context when the
   goal asks for next roadmap work.
3. Penalize historical generated review/amendment summaries for current-planning goals unless the
   user explicitly asks for historical review material.
4. Promote implementation files and tests when authority docs name them or when the query asks for
   implementation work.
5. Make cold-start command output clearer about when indexed query requires applied ingest, while
   keeping preview-first safety intact.
6. Revisit generated state placement or first-run messaging so a first-time repository does not
   feel polluted after a normal evaluation run.

## Recommended Acceptance Bar For The Next Fix

The next implementation slice should include fixture-backed and live-shape regression coverage for
the cases exposed here:

- hocrgen-style refreshed source state: exact current slice notation such as `F6f` must retrieve
  current authority records above stale generated review summaries.
- hocrgen-style provider queries: implementation files and tests should rank above broad historical
  spinout discussion when the query asks for provider-gate implementation work.
- hocrsyngen-style cold start: when no sources are ingested, the command should either use
  provisional current authority well enough to name the next slice or explicitly say that indexed
  retrieval requires ingest.
- hocrsyngen-style applied ingest: when query can retrieve the current slice, `brief` and
  `suggest-next` must promote that slice into work actions instead of leaving it in relevant
  matches below merged PR review suggestions.
- completed-slice evidence should remain visible only as predecessor context, not as a default
  next action.

## Out Of Scope For This Intake

This document and the raw reviewer replies do not change runtime behavior, add tests, or update
planning-state lines. They preserve the v0.5.1 external retry evidence so the next implementation
PR can target the remaining handoff-ranking and current-planning gaps directly.
