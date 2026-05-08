# Splendor v0.5.2 hocrgen / hocrsyngen Retry Findings

This document summarizes the v0.5.2 hocrgen and hocrsyngen retry replies after the
current-work handoff ranking fix was packaged as a release wheel. It is synthesis over the raw
reviewer replies, not a runtime behavior change.

## Source Materials

- [hocrgen retry reply](v0_5_2_hocrgen_retry_reply.md)
- [hocrgen follow-up reply](v0_5_2_hocrgen_followup_reply.md)
- [hocrsyngen retry reply](v0_5_2_hocrsyngen_retry_reply.md)
- [hocrsyngen follow-up reply](v0_5_2_hocrsyngen_followup_reply.md)

## Review Scope

The retry asked whether `v0.5.2` fixed the blocker exposed by the v0.5.1 hocrgen/hocrsyngen
retry: Splendor could retrieve some current planning evidence, but `brief --agent-context` and
`suggest-next` still promoted merged PR history above the actual current work.

`v0.5.2` specifically packaged the M20-P1.4 current-work handoff ranking fix. The intended
question was narrow:

> Does Splendor now identify the current next hocrgen / hocrsyngen slice instead of leading with
> merged PR review history?

## Partner Verdicts

| Partner | Verdict | Positive signal | Blocking signal |
| --- | --- | --- | --- |
| hocrgen | No | Some useful roadmap, public-beta, and implementation context surfaced | Handoff still led with stale `F1c`, not actual next `F6f2` |
| hocrsyngen | Maybe | `brief` and `suggest-next` led with active `S8b` from `.agent-plan.md` | `query` still failed as an answer surface; onboarding and maintenance noise remain |

## hocrgen Result

The hocrgen retry is a hard failure for the v0.5.2 adoption question.

Direct hocrgen repository truth said:

- the last completed roadmap action was `F6f2a`;
- the next unchecked slice was `F6f2`;
- `F6g` was also unchecked, but gated behind more evidence;
- there were no open GitHub issues or pull requests.

Splendor instead reported:

- `current_planned_work.slice_id: F1c`;
- `authority_paths: ["docs/HeOCR_hocrgen_long_term_roadmap.md"]`;
- first action: `Continue F1c from current planning authority`;
- next actions: merged PRs `#43`, `#70`, `#72`, and `#45`.

The hocrgen follow-up confirmed the same failure from exact JSON excerpts after targeted refresh
and ingest. The failing reason text came from an old roadmap blocker sentence:

> The current known blocker remains: full synthetic target scale still requires a larger validated
> hocrsyngen batch.

That is useful context, but it is not the next work item. Splendor treated blocker prose containing
`F1c` as current planned work and failed to prioritize the active unchecked `.agent-plan.md` task
state.

### hocrgen Classification

- `brief --agent-context`: fail.
- `suggest-next`: fail.
- `query`: fail as a standalone handoff/answer surface.
- Adoption status: no.
- Core blocker: current-work extraction prefers stale roadmap blocker prose over unchecked
  `.agent-plan.md` task state.

## hocrsyngen Result

The hocrsyngen retry is a partial pass for the v0.5.2 handoff goal.

Direct hocrsyngen repository truth said:

- active item: `S8b: Wet-test smoke run artifact generator`;
- next planned slice after S8b: `S8c` human-first static gallery;
- roadmap and production-readiness docs agreed that Phase S8 was current.

Splendor behavior:

- cold-start `brief --agent-context` led with `Continue S8b from current planning authority
  target=.agent-plan.md`;
- cold-start `suggest-next` led with the same S8b action and cited `.agent-plan.md`;
- cold-start `query "current hocrsyngen next planned slice"` returned no matches;
- after manual source setup and ingest, `brief` and `suggest-next` still led with S8b;
- after ingest, `query` improved to seven matches but still did not answer the handoff question.

The hocrsyngen follow-up accepted this classification: `brief` and `suggest-next` are partial
passes, `query` remains a failure as a standalone handoff surface, and adoption is "maybe" for
brief/suggest-next with manual verification.

### hocrsyngen Classification

- `brief --agent-context`: partial pass.
- `suggest-next`: partial pass.
- `query`: fail as a standalone handoff/answer surface.
- Adoption status: maybe, for brief/suggest-next only and with manual verification.
- Core blocker: query-answering, cold-start onboarding, stale PR clutter, branch/planning mismatch
  surfacing, and generated review-state noise.

## Cross-Cutting Insights

### 1. `.agent-plan.md` Needs Stronger Current-Task Semantics

The hocrsyngen success and hocrgen failure point to the same contract boundary. When
`.agent-plan.md` clearly names active or unchecked current work, that signal should outrank old
roadmap prose, generated summaries, and merged PR history. In hocrsyngen, Splendor used
`.agent-plan.md` correctly. In hocrgen, it did not.

The next fix should make active/unchecked task extraction from `.agent-plan.md` a first-class
handoff signal, not merely another text match.

### 2. Blocker Prose Is Context, Not A Current Slice

hocrgen failed because a sentence about a current known blocker included `F1c`. That does not make
`F1c` the next implementation slice. Splendor needs to distinguish:

- active unchecked task;
- completed/current status table row;
- blocker or prerequisite text;
- historical review or amendment context;
- merged PR evidence.

Blocker prose should support the reason for a next action only when it maps back to an active
unchecked or explicitly current planned item.

### 3. Merged PRs Still Clutter Handoff

Both reviewers saw stale merged PR history immediately after the top handoff action. In hocrgen,
that clutter compounded the wrong answer. In hocrsyngen, it did not displace S8b, but it still made
the output feel less trustworthy.

Merged PRs should remain predecessor context for current-work goals unless the user explicitly asks
for history, review, or release archaeology.

### 4. `query` Is Still Search, Not Handoff Answering

Both retries rejected `query` as a standalone answer surface. hocrgen saw irrelevant or stale
search ranking. hocrsyngen saw no cold-start matches and then post-ingest matches that still did
not answer "what is current / next?"

This is a separate product gap from `brief` and `suggest-next`. It should not block fixing the
handoff action ranking, but it should be tracked as an explicit answer-synthesis or
authority-answer mode if Splendor wants `query` to handle current-work questions.

### 5. Cold-Start And Generated-State Noise Still Hurt Adoption

hocrsyngen still found the source setup path awkward: `ingest --pending --apply` had no work until
sources were manually added, and generated contested/review-needed state looked scarier than it was.
That does not invalidate the S8b handoff pass, but it remains adoption friction.

## Conclusions

`v0.5.2` should not be treated as a general hocr adoption success.

It produced a real partial win: hocrsyngen can use `brief` and `suggest-next` again for current
work, with manual verification. But hocrgen still fails the core handoff test because Splendor
selects stale `F1c` blocker prose instead of the active `F6f2` unchecked task.

The next Splendor fix should focus on a narrow current-work authority model:

1. Extract active/unchecked `.agent-plan.md` tasks as first-class current-work candidates.
2. Parse roadmap/status-table state so completed/current references do not become next actions.
3. Treat blocker prose as context unless it maps to active planned work.
4. Suppress merged PR history for current-work goals unless history is explicitly requested.
5. Demote superseded refreshed source summaries when fresher authority exists.
6. Add hocrgen regression coverage where the expected top handoff is `F6f2`, with `F6g` gated
   behind it and `F1c` preserved only as blocker context.

`query` answer synthesis, cold-start source setup, branch/planning mismatch surfacing, and
generated contradiction-review noise are important follow-ups, but they should not be allowed to
blur the immediate hocrgen blocker: the top current-work handoff answer is wrong.

## Recommended Next Acceptance Bar

A focused fix should pass these checks before another hocrgen retry:

- For the captured hocrgen shape, `brief --agent-context "continue the current hocrgen roadmap
  work"` ranks `F6f2` first.
- `suggest-next "continue the current hocrgen roadmap work"` ranks `F6f2` first.
- `F6g` appears only as gated/follow-on context behind `F6f2`.
- `F1c` appears only as blocker/prerequisite context, not as `current_planned_work.slice_id`.
- Merged PRs do not appear as top actions for current-work goals.
- hocrsyngen still ranks `S8b` first for its current-work handoff.
