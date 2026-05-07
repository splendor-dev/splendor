# v0.5 SynthBanshee Integrated-Use Review Summary

## Scope

This folder preserves the SynthBanshee integrated-use review of Splendor v0.5.0. The reviewer had
already judged v0.4.0 fit for day-to-day use and had been using Splendor inside SynthBanshee; this
round checks the v0.5.0 release against the follow-up issues that emerged from real integrated
usage rather than from a fresh adoption trial.

Raw inputs:

- `claude_review.md`
- `claude_followup_reply.md`

## Verdict

The v0.5.0 review accepts the M19 blocker loop as closed. Legacy mutating preview/apply safety,
generated-text integrity, completion-aware handoff inference, broader related work-thread
surfacing, cold-start/PATH hardening, and the main policy-cited read-first behavior are materially
better than v0.4.0. No v0.5.x patch loop is justified by this review.

The remaining items are polish follow-ups that can ride with Milestone 20 work:

- #160: goal phrasing can still displace policy-cited read-first files from the top slots.
- #161: one maintenance-oriented `splendor wiki suggest` line still leaks into the work footer.
- #162: no-diff `pr-summary --since <ref>` remains too quiet in human output.
- #163: `queue clean --json` now emits the canonical `mutation` contract, but also keeps redundant
  legacy top-level aliases.

Issue #156 should be treated as closed by v0.5.0 because M19-P7.1 now surfaces parent and sibling
work threads instead of a single open issue.

## Follow-Up Disposition

| Issue | Disposition | Recommended scope |
| --- | --- | --- |
| #156 | Close as completed. | No follow-up work; v0.5.0 now surfaces bounded related parent/sibling work threads. |
| #160 | Keep open, retitle/reframe. | Add a focused regression for goal-sensitive ranking where surfaced authority docs name implementation/test paths but goal-token scoring pushes them out of the read-first list. |
| #161 | Keep open, narrow. | Remove the remaining `splendor wiki suggest <source-id>` maintenance action from the `brief --agent-context` work footer or move it to the maintenance block only. |
| #162 | Keep open, narrow. | Make no-diff human output short-circuit loudly when `head == merge_base` or `Changed paths == 0`; JSON improvements alone are not enough. |
| #163 | Keep open, reframe as deprecation policy. | Treat `mutation.{mode,mutates,planned,written}` as canonical, keep verb-specific payloads, mark top-level aliases deprecated in v0.5.x docs, and plan alias removal in v0.6.0. |
| #157, #158, #159 | Leave open as P2/P3 polish. | Not blockers for v0.5.0 and not part of the M20 handoff unless they become relevant to the selected slice. |

## Planning Impact

The review supports moving the active roadmap state from the final M19 durability slice to the first
M20 product bet. M20 should start with `M20-P1.1` advanced semantic search or vector index work,
while keeping #160-#163 visible as bounded polish follow-ups that should not reopen the M19 cleanup
loop.
