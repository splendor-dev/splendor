# Splendor v0.4 External Review Round Summary

This document summarizes the v0.4.0 external review round before translating the findings into
product design, roadmap, or planning-state changes. It is synthesis over the raw partner notes, not
a new planning authority.

## Source Materials

- [hocrgen evaluation](v0_4_hocrgen_evaluation.md)
- [hocrgen follow-up](v0_4_hocrgen_reply.md)
- [hocrgen calibration reply](v0_4_hocrgen_calibration_reply.md)
- [SynthBanshee prompt](v0_4_synthbanshee_prompt.md)
- [SynthBanshee evaluation](v0_4_synthbanshee_reply.md)
- [SynthBanshee follow-up reply](v0_4_synthbanshee_followup_reply.md)
- [hocrsyngen prompt](v0_4_hocrsyngen_prompt.md)
- [hocrsyngen evaluation](v0_4_hocrsyngen_reply.md)
- [hocrsyngen follow-up reply](v0_4_hocrsyngen_followup_reply.md)

## Review Scope

The round tested v0.4.0 after the M18 work-first handoff slices and the M19 preview/apply,
generated-state, and queue-cleanup slices. The partners covered three different adoption modes:

- `hocrgen`: returning design partner, testing whether Splendor can infer the next current roadmap
  slice after recently merged work.
- `SynthBanshee`: returning design partner, testing whether v0.4.0 fixed the v0.3 git-blind and
  maintenance-dominance handoff failures.
- `hocrsyngen`: first-time partner, testing cold-start setup plus branch/PR/roadmap handoff in a
  repository that had not adopted Splendor.

## Partner Verdicts

| Partner | Verdict | Main positive signal | Main failure signal |
| --- | --- | --- | --- |
| hocrgen | Not yet first tool | Better context pack; maintenance no longer dominated | Failed to infer `F4c` after completed `F3b` |
| SynthBanshee | Crossed the line | `brief` and `suggest-next` led with issue `#91`; queue-clean orphans fixed | Legacy mutate-on-call commands remain unsafe |
| hocrsyngen | Not ready for adoption | Useful file index and PR-context aggregator | Failed to infer `S4d` after merged `S4c`; first-run state churn felt unsafe |

## What Improved Since v0.3

- Git-aware handoff is materially better. SynthBanshee saw recent commits, PR context, and the next
  open work thread ranked above maintenance.
- Maintenance separation is mostly working. Source freshness, queue state, and wiki review state are
  discoverable without crowding out work in the main handoff sections.
- Queue cleanup closure is validated. `queue clean --orphaned` previewed the exact orphan records
  that SynthBanshee previously could only remove manually.
- Provisional uncurated context is useful. Partners noticed when important repo docs surfaced with
  curation hints instead of being silently ignored.
- Compact generated-state review and PR-summary caveats reduced some of the earlier reviewability
  pain, though they did not eliminate cold-start state churn concerns.

## What Still Failed

- Current-state inference is not completion-aware enough. hocrgen and hocrsyngen both had enough
  git/GitHub/roadmap evidence to infer the next slice, but Splendor still sent the handoff back to
  recently merged work.
- Preview/apply consistency is incomplete. New cleanup paths teach preview-first behavior, while
  legacy verbs such as `ingest --pending` still mutate on call.
- Work-thread surfacing is too narrow. SynthBanshee found that the top issue was correct, but the
  related open parent and sibling issues did not appear.
- Cold-start adoption is too noisy. hocrsyngen observed many visible top-level generated files after
  first-run setup and minimal seeding.
- Some implementation surfaces are missed even when authority docs name them. SynthBanshee expected
  `synthbanshee/tts/renderer.py` and `tests/unit/test_effective_prosody_cap.py` to appear because
  the ASR policy names their symbols.

## Cross-Cutting Takeaways

1. v0.4.0 validated the M18 direction: work-first, git-aware handoff can make Splendor the first
   command an external coding agent runs.
2. The next safety gap is legacy mutation behavior. The new queue cleanup command makes the old
   mutate-on-call commands more surprising, not less, because the CLI now teaches mixed semantics.
3. The next handoff-quality gap is completion-aware planning inference: merged slice plus ordered
   roadmap should imply the next open slice, even when dynamic planning docs are stale.
4. Cold-start ergonomics matter separately from handoff correctness. A first-time repo can tolerate
   less state only if Splendor clearly explains where that state will live and how to review or
   discard it.
5. The raw evaluation notes are evidence, not planning state. Product/design changes should cite
   them through a findings register or roadmap update rather than treating the raw partner replies
   as durable requirements.

## Agreed Priority Signals

SynthBanshee chose legacy preview/apply harmonization first, then multi-issue work-thread surfacing,
then polish. Its reason was safety: v0.4.0 made the preview/apply asymmetry more dangerous by adding
new preview-first commands next to older drain verbs.

hocrgen and hocrsyngen both selected completion-aware current-state inference as the blocker for
their next trial. Both failures involved the same pattern: recently completed work remained ranked as
next work when the roadmap pointed to the following slice.

The combined sequence suggested by the review round is:

1. Legacy preview/apply harmonization for mutating maintenance/workflow verbs.
2. Completion-aware current-state planning inference.
3. Broader work-thread surfacing for related open issues.
4. Cold-start/local-state ergonomics.
5. Focused robustness and polish: PATH-safe git lookup, policy-cited path boosting, clearer no-diff
   PR summaries, and removal of trailing maintenance next-actions.

## Out Of Scope For This PR

This intake PR intentionally does not update `.agent-plan.md`, roadmap planning state, product
specs, command behavior, or tests. Those changes should land in follow-up implementation/design PRs
with their own scoped validation.
