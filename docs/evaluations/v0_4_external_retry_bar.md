# v0.4 External Retry Bar

This document records the accepted v0.4 requirements synthesized from the raw v0.3 SynthBanshee and
hocrgen evaluations. The raw reports remain evidence; this file is the concise handoff authority for
the next implementation slices.

## Source Reports

- [v0.3 SynthBanshee evaluation](v0_3_synthbanshee_evaluation.md)
- [v0.3 SynthBanshee follow-up](v0_3_synthbanshee_followup.md)
- [v0.3 hocrgen evaluation](v0_3_hocrgen_evaluation.md)
- [v0.3 hocrgen follow-up](v0_3_hocrgen_followup.md)

## Accepted v0.4 Goal

Splendor v0.4 should make external agents start with `splendor brief --agent-context` and
`splendor suggest-next` before reaching for `git log`, GitHub issue/PR inspection, `rg`, and direct
planning-file reads.

## Required Handoff Shape

- Lead with the next real work item, current planning authority, and the files/tests needed to act.
- Include recent relevant git, issue, and PR context by default, with explicit escape hatches for
  narrower or git-free output.
- Keep source freshness, queue drift, missing synthesis, review-needed pages, and other Splendor
  maintenance state in a separate maintenance section unless the goal explicitly asks for
  maintenance.
- Rank current roadmap, `.agent-plan.md`, accepted policy docs, and recent implementation context
  above historical outside reviews and raw evaluation reports.
- When important docs are not curated sources, show them as clearly labeled provisional context
  rather than omitting them or treating them as reviewed source authority.

## SynthBanshee Retry Bar

For `splendor brief --agent-context "pick up M17 ASR work"`, the handoff should surface:

- the next open ASR issue or PR thread, with link and one-line summary
- the recent effective-prosody PR context
- ASR sanity-check policy
- relevant validation report
- renderer and test files needed for the next implementation step
- Splendor maintenance state only after the work context

## hocrgen Retry Bar

For `splendor brief --agent-context "Resume hocrgen planning after F3a"`, the handoff should
surface:

- `F3b` as the next implementation step
- `.agent-plan.md` and the current roadmap critical path
- the modern handwritten acquisition policy
- README/CONTRIBUTING and relevant planning tests
- the recent F3a PR context
- historical outside reviews only after current planning authority

## Planned Implementation Issues

- [M18-P1.1 Add git-aware, work-first agent handoff](https://github.com/splendor-dev/splendor/issues/139)
- [M18-P2.1 Add inferred authority and provisional uncurated-doc context](https://github.com/splendor-dev/splendor/issues/140)
- [M18-P3.1 Improve handoff reviewability and maintenance discoverability](https://github.com/splendor-dev/splendor/issues/141)
