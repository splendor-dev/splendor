# Splendor v0.4 External Findings Register

This register distills the v0.4.0 external review round into actionable findings. It should inform
future design and planning updates, but it is not itself a committed roadmap.

Severity legend:

- `P1`: blocks safe or trustworthy agent handoff in at least one partner workflow.
- `P2`: frequent workflow drag or adoption risk, but workaround exists.
- `P3`: polish or clarity issue that should not block the next implementation slice.

## Findings

| ID | Finding | Evidence | Affected surface | Severity | Recommended next action |
| --- | --- | --- | --- | --- | --- |
| V04-F1 | Legacy mutating verbs still need preview/apply harmonization. | SynthBanshee v0.4 evaluation and follow-up. The reviewer singled out `ingest --pending`, `source refresh`, `source update-path`, and `workspace refresh`. | CLI mutation contracts, queue/ingest/source/workspace flows | P1 | Add preview-first/apply semantics or split/rename destructive forms. Treat as the next safety slice. |
| V04-F2 | Completion-aware current-state inference is missing. | hocrgen expected `F4c` after completed `F3b`; hocrsyngen expected `S4d` after merged `S4c`. | `brief --agent-context`, `suggest-next`, planning inference | P1 | Combine git/GitHub merge state, dynamic planning docs, and roadmap ordering to infer the next open slice. |
| V04-F3 | Work-thread issue surfacing is too narrow. | SynthBanshee surfaced issue `#91` correctly but missed related open ASR issues `#87`, `#88`, and `#92`. | GitHub issue context in handoff | P2 | Show the top 3-5 goal-relevant open issues/work threads, not only the single best match. |
| V04-F4 | First-run state churn feels unsafe in cold-start repos. | hocrsyngen observed top-level Splendor directories and 80+ untracked files after minimal setup and seeding. | `init`, source seeding, generated/local state layout | P2 | Improve cold-start ergonomics: clearer state-location disclosure, local/hidden workspace option, or better review grouping. |
| V04-F5 | PATH-unsafe subprocess git lookup can crash cold-start use. | hocrsyngen hit `NotADirectoryError: [Errno 20] Not a directory: 'git'` until `PATH` was sanitized. | Git subprocess discovery | P2 | Harden command lookup against non-directory `PATH` entries and add a regression test. |
| V04-F6 | Policy-cited implementation files need ranking boosts. | SynthBanshee expected `synthbanshee/tts/renderer.py` and `tests/unit/test_effective_prosody_cap.py` because authority docs named `_EFFECTIVE_*` and cap policy. | Files-to-read ranking | P2 | Parse or boost paths/symbols cited by high-authority docs when assembling first-read files. |
| V04-F7 | Trailing maintenance next-actions can undercut work-first separation. | SynthBanshee said top sections separated maintenance well, but bottom next-action lines still suggested maintenance commands. | Human `brief --agent-context` output | P3 | Keep maintenance commands only in the maintenance block unless the goal is maintenance. |
| V04-F8 | `pr-summary --since main` no-diff state could be clearer. | SynthBanshee noted clean `main` produced a degenerate `changed_paths: 0` probe. | `pr-summary` human output | P3 | Detect `head == merge_base` and say explicitly that there is no diff against the selected base. |
| V04-F9 | JSON mutation vocabulary is slightly inconsistent with release prose. | SynthBanshee saw deterministic `queue clean --json` output, but field names differed from release-note prose. | JSON mutation/reporting contracts | P3 | Align or document field names such as `mode`, `mutation`, `planned`, and `written` consistently. |
| V04-F10 | Scan ranking can be too broad for first-run handoff. | hocrsyngen reported core handoff files competing with licenses, fixture corpora, and broad docs. | `repo scan`, first-use curation | P3 | Add stronger first-run ranking for `AGENTS.md`, `.agent-plan.md`, README, roadmap, and nearby tests/code. |
| V04-F11 | Ingest needs progress feedback for long drains. | hocrsyngen observed `ingest --pending` remaining silent for roughly a minute. | Ingest command UX | P3 | Add deterministic progress/status output where it does not break JSON contracts. |
| V04-F12 | Lint may report repo-relative README links as missing. | hocrsyngen reported false positives for links such as `docs/roadmap.md`. | `splendor lint` docs/link checks | P3 | Reproduce and fix link resolution, or narrow the diagnostic until it is reliable. |

## Validated Improvements

| ID | Improvement | Evidence | Follow-up |
| --- | --- | --- | --- |
| V04-S1 | Work-first handoff crossed the line for SynthBanshee. | SynthBanshee would now start with `splendor brief --agent-context`. | Preserve this behavior while fixing safety and breadth issues. |
| V04-S2 | Queue orphan cleanup is now a real closure path. | SynthBanshee verified `queue clean --orphaned` previews all nine orphan records, including the v0.3 reproducer. | Preserve preview/apply and JSON contract behavior when harmonizing other verbs. |
| V04-S3 | Maintenance separation is materially better. | SynthBanshee and hocrgen saw maintenance state separated from primary work more clearly than v0.3. | Avoid regressing this when adding more issue/context signals. |
| V04-S4 | Provisional uncurated context is useful. | Partners noticed relevant uncurated docs appearing with curation hints. | Keep provisional labels clear and avoid silently promoting unreviewed sources to authority. |

## Suggested Sequencing

The review round does not settle exact milestone names, but it does give a practical order:

1. **Safety first:** address V04-F1, because mixed mutation semantics can destroy exploratory
   handoff safety.
2. **Handoff correctness second:** address V04-F2, because two partners failed the same
   completed-slice-to-next-slice inference test.
3. **Handoff breadth third:** address V04-F3 and V04-F6 together if scope allows.
4. **Cold-start adoption fourth:** address V04-F4 plus the narrower V04-F5 robustness bug.
5. **Polish later:** address V04-F7 through V04-F12 as scoped follow-ups or opportunistic fixes.

## Non-Decisions

- This register does not choose the next PR sub-slice name.
- This register does not update product or roadmap commitments.
- This register does not change the v0.4.0 release notes.
- This register does not decide whether raw external notes should remain unedited long term.
