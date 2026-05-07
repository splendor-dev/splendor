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

## Post-Round Follow-Up Findings

These findings were filed as GitHub issues after the original v0.4 external review round. They are
kept separate from the round findings above so the historical review record stays intact, but they
now affect the accepted M19 sequence because they expose generated-state correctness risks.

| ID | Finding | Evidence | Affected surface | Severity | Recommended next action |
| --- | --- | --- | --- | --- | --- |
| V04-F13 | Generated Evidence/Contradictions text can leak control bytes. | SynthBanshee follow-up issue #165 reports UTF-8 punctuation from clean source docs becoming BEL, partial UTF-8 bytes, digit substitutions, and YAML `\xNN` escapes in generated wiki pages and review tasks. | Ingest generation, evidence extraction, wiki/task markdown, YAML frontmatter | P1 | Fix the encoding/sanitization path and add regression coverage proving generated markdown/YAML contains no control bytes. Treat as an immediate bugfix before broader handoff work. |
| V04-F14 | Manifest `pipeline_version` provenance can stay stale after path repair plus ingest. | SynthBanshee follow-up issue #164 reports manifests retaining old `pipeline_version` values after `source update-path` and ingest rewrite `last_run_id`, while run records and wiki pages reflect the newer Splendor version. | Source manifests, ingest provenance, source path repair | P1 | Refresh manifest `pipeline_version` whenever ingest/source refresh rewrites manifest provenance, or document immutable semantics with a migration path. Include this in `M19-P5.2` with V04-F13. |

## Post-v0.5 Disposition

The v0.5 SynthBanshee integrated-use review closes the M19 blocker loop and turns this register into
historical evidence plus follow-up triage. The original recommended actions below are no longer the
active implementation queue unless the disposition says a follow-up issue remains open.

| ID | v0.5 disposition | Current tracking |
| --- | --- | --- |
| V04-F1 | Implemented by `M19-P5.1`: legacy mutating maintenance/workflow verbs now preview by default and require explicit `--apply` for writes. | Closed M19 work. |
| V04-F2 | Implemented by `M19-P6.1`: handoff inference reconciles stale dynamic planning docs with ordered roadmap and recent mainline evidence. | Closed M19 work. |
| V04-F3 | Implemented by `M19-P7.1`: bounded related parent/sibling work threads now surface; issue #156 is closed. | Closed M19 work. |
| V04-F4 | Implemented by `M19-P8.1` through first-run state location/review clarity. The v0.5 integrated-use reviewer accepted this from release notes and local coverage, but did not rerun a fresh cold-directory test. | Closed M19 blocker; no new issue unless fresh cold-start use reproduces churn. |
| V04-F5 | Implemented by `M19-P8.1`: PATH-safe git lookup no longer crashes on empty or malformed PATH probes, and regression coverage exists. | Closed M19 work. |
| V04-F6 | Materially improved by `M19-P7.1`, but goal phrasing can still displace authority-cited paths from the top read-first slots. | Follow-up #160 under Milestone 20. |
| V04-F7 | Materially improved by `M19-P7.1`, but one `splendor wiki suggest <source-id>` maintenance action still leaks into the work footer. | Follow-up #161 under Milestone 20. |
| V04-F8 | Partially improved for JSON, but human no-diff `pr-summary` output still needs a louder short-circuit. | Follow-up #162 under Milestone 20. |
| V04-F9 | Partially improved: `mutation` is now present, but `queue clean --json` still emits redundant legacy aliases. | Follow-up #163 under Milestone 20. |
| V04-F10 | Not addressed by M19; still acceptable polish. | Open only if first-run scan ranking becomes relevant to a later slice. |
| V04-F11 | Not addressed by M19; still acceptable polish. | Open only if ingest progress becomes relevant to a later slice. |
| V04-F12 | Not addressed by M19; still acceptable polish. | Open only if lint link resolution is reproduced. |
| V04-F13 | Implemented by `M19-P5.2`: generated text integrity checks and sanitization cover control-byte leakage. | Closed M19 work. |
| V04-F14 | Implemented by `M19-P5.2`: manifest `pipeline_version` provenance is refreshed when ingest rewrites manifest provenance. | Closed M19 work. |

## Validated Improvements

| ID | Improvement | Evidence | Follow-up |
| --- | --- | --- | --- |
| V04-S1 | Work-first handoff crossed the line for SynthBanshee. | SynthBanshee would now start with `splendor brief --agent-context`. | Preserve this behavior while fixing safety and breadth issues. |
| V04-S2 | Queue orphan cleanup is now a real closure path. | SynthBanshee verified `queue clean --orphaned` previews all nine orphan records, including the v0.3 reproducer. | Preserve preview/apply and JSON contract behavior when harmonizing other verbs. |
| V04-S3 | Maintenance separation is materially better. | SynthBanshee and hocrgen saw maintenance state separated from primary work more clearly than v0.3. | Avoid regressing this when adding more issue/context signals. |
| V04-S4 | Provisional uncurated context is useful. | Partners noticed relevant uncurated docs appearing with curation hints. | Keep provisional labels clear and avoid silently promoting unreviewed sources to authority. |

## Historical M19 Sequencing

The review round set the original M19 order. The post-round follow-up findings above inserted one
generated-state safety slice before completion-aware handoff inference resumed. This sequence is now
complete as of v0.5.0:

1. **`M19-P5.1` safety first:** address V04-F1, because mixed mutation semantics can destroy
   exploratory handoff safety.
2. **`M19-P5.2` generated-state correctness before handoff inference:** address both V04-F13 and
   V04-F14, because corrupted generated artifacts and stale provenance undermine the state later
   handoff commands depend on.
3. **`M19-P6.1` handoff correctness second:** address V04-F2, because two partners failed the
   same completed-slice-to-next-slice inference test.
4. **`M19-P7.1` handoff breadth third:** address V04-F3 and V04-F6 together if scope allows.
5. **`M19-P8.1` cold-start adoption fourth:** address V04-F4 plus the narrower V04-F5 robustness
   bug.
6. **Polish later:** V04-F7 through V04-F12 remain scoped follow-ups only where the post-v0.5
   disposition table names an active issue.

## Non-Decisions

- This register records the historical M19 sequencing and the post-v0.5 disposition; it is still not
  itself a committed roadmap.
- This register does not implement product behavior.
- This register does not change the v0.4.0 release notes.
- This register does not decide whether raw external notes should remain unedited long term.
