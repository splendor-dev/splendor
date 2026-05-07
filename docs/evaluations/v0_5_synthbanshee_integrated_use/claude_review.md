# Splendor v0.5.0 — Review Report

## Install & Version

```bash
uv tool install --reinstall \
  https://github.com/splendor-dev/splendor/releases/download/v0.5.0/splendor-0.5.0-py3-none-any.whl
~/.local/bin/splendor --version
# → splendor 0.5.0
```

`.venv/bin/splendor` is unchanged at `0.2.0` — PATH precedence trap is unchanged. Always use `~/.local/bin/splendor`.

## Review Commands Run

```bash
~/.local/bin/splendor brief --agent-context "pick up M17 ASR work"
~/.local/bin/splendor brief --agent-context "what's the current state of the SynthBanshee active milestone"
~/.local/bin/splendor suggest-next "what's the current SynthBanshee active work"
~/.local/bin/splendor source refresh --help
~/.local/bin/splendor ingest --help
~/.local/bin/splendor workspace refresh --help
~/.local/bin/splendor source update-path --help
~/.local/bin/splendor source refresh AGENTS.md --json     # preview-mode contract probe
~/.local/bin/splendor queue clean --orphaned --json       # JSON contract probe (#163)
~/.local/bin/splendor ingest --pending --json             # preview-mode contract probe
~/.local/bin/splendor pr-summary --since main             # degenerate head==merge_base (#162)
~/.local/bin/splendor pr-summary --since main --json
~/.local/bin/splendor health --json
~/.local/bin/splendor lint --json
PATH="" ~/.local/bin/splendor brief --agent-context "test"             # PATH-safe git
PATH="/nonexistent:/tmp:/usr/local/bin" ~/.local/bin/splendor brief …
PATH="/usr/bin:/bin" ~/.local/bin/splendor brief …
# control-byte scan: find planning wiki state … | xargs grep -lP '[\x00-\x08\x0e-\x1f\x7f]'
# trailing newline check: tail -c 30 planning/tasks/task-review-*.md | xxd
ls -la CLAUDE.md AGENTS.md   # symlink confirmation (#157)
```

## Verdict: Mostly Closed with Caveats

All blockers (A apply-gate, B multi-issue surfacing) are closed. All correctness/safety items in the codex framing are addressed. Four polish residuals remain — none of them block use, none of them require a v0.5.x patch loop.

## Codex Framing — 8 Areas

| # | Area                                                  | Status                                                                                                                                                                     |
| - | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Legacy mutating preview/apply harmonization           | Fixed — `--apply` uniformly required; `mutation.{mode,mutates,planned}` consistent                                                                                         |
| 2 | Generated text control-byte sanitization (#165)       | Fixed — clean scan of `planning/`, `wiki/`, `state/`                                                                                                                       |
| 3 | Manifest provenance after path repair + ingest (#164) | Fixed — issue closed via PR #167; not reproduced this trial                                                                                                                |
| 4 | Completion-aware handoff (M19-P6.1)                   | Fixed — #91 / PR #95 demoted from suggestions, parent #87 + siblings remain                                                                                                |
| 5 | Broader related work-thread surfacing (#156)          | Fixed — `[high/work-thread]` shows 3–4 issues with parents/siblings                                                                                                        |
| 6 | Policy-cited file surfacing (#160)                    | Materially improved but still imperfect — `mixer.py` boosted; `renderer.py` + `test_effective_prosody_cap.py` missed on the M17-specific goal but present on broader goals |
| 7 | Cold-start / custom-layout state review               | Trusting release notes — not exercised in cold dir; `splendor init --help` is bare; not in the 9                                                                           |
| 8 | PATH-safe git lookup                                  | Fixed — `PATH=""` and `PATH="/nonexistent…"` both fall back gracefully without crash, no Git context: line                                                                 |

## Codex Framing — 7 Earlier Recommendations

| # | Recommendation                                     | Status                                                                                                                                                                                                                        |
| - | -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Harmonize preview/apply for legacy verbs           | Fixed                                                                                                                                                                                                                         |
| 2 | Surface 3–5 work-relevant open issues              | Fixed                                                                                                                                                                                                                         |
| 3 | Boost files cited by authority/policy docs         | Materially improved but still imperfect                                                                                                                                                                                       |
| 4 | Drop trailing maintenance next-action noise        | Materially improved but still imperfect — one `splendor wiki suggest` verb still leaks into the work footer                                                                                                                   |
| 5 | Anchor specific authority sections, not just files | Not addressed, acceptable polish — boost is still file-level only                                                                                                                                                             |
| 6 | Louder no-diff `pr-summary --since main`           | Materially improved but still imperfect — JSON gains a `compact_committed` mode tag, human output still says only `Changed paths: 0`                                                                                          |
| 7 | Tighten JSON mutation vocabulary                   | Materially improved but still imperfect — `queue clean --json` ships both the v0.4 schema (`applied`/`summary.{planned,written,skipped}`/`actions`) and the documented mutation block side-by-side; pick one or document both |

## Of the Original 9 Issues (#155–#163)

* Fixed (4): #155, #156, #160 (mostly), #161 (mostly).
* Materially improved but still imperfect (2): #162, #163.
* Not addressed, acceptable polish (3): #157 (symlink dup), #158 (trailing newline — sampled v0.4-generated files all end in `\n`; unverified for fresh v0.5 generation), #159 (`splendor run prune`).
* Blockers remaining: 0.

## Recommendation: Move to M20

v0.5.0 is strictly better than v0.4.0 for SynthBanshee day-to-day. M19 cleanup is done; the four polish residuals (#160 goal-sensitivity, #161 single leaky verb, #162 no-diff signal, #163 JSON contract coexistence) can ride on M20 work — they don't justify a dedicated v0.5.x patch cycle.

Two of those residuals are interesting enough that splendor may want them as new tightly-scoped follow-up issues:

* #160 goal-phrasing sensitivity: the read-first boost surfaces `renderer.py` for goal "current state of the milestone" but not for goal "pick up M17 ASR work" — looks like a score-weighting interaction with goal-token similarity that suppresses authority-cited paths when a more specific token is in the goal. Worth a focused regression issue against splendor.
* #163 schema coexistence rather than harmonization: documented vocabulary now exists under `mutation`, but the legacy top-level `applied`/`summary` fields are still emitted alongside. Pick one as canonical or document both as supported.

Memory updated: `project_splendor_eval_v050_2026_05_08.md` (new), `MEMORY.md` index, v0.4 memo flagged superseded.
