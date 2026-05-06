**1. Verdict**
I would still start hocrgen work with direct `rg`, git, and docs. Splendor v0.4.0 is better as a context pack than v0.3, but it did not cross the line: for the actual resume task it failed the core test. It surfaced F3b/F3a history and some right authority docs, but it did not identify `F4c` as the next implementation task even though that is explicit in [.agent-plan.md](/Users/shaypalachy/clones/hocrgen/.agent-plan.md:20) and the roadmap.

Verified install: `/tmp/splendor-v040/bin/splendor --version` returned `splendor 0.4.0` from the GitHub release wheel.

**2. Actual Top Handoff**
`brief --agent-context` first visible handoff items:

1. Review PR #64: `F3b: Implement bounded modern handwriting acquisition workflow`
2. Review PR #63: `F3a: Define rights-clean modern handwritten acquisition policy`
3. Review commit `da1a1b6`: F3b
4. Review commit `821c244`: D2a source-health paths
5. Review commit `b10c78d`: E4a governance controls
6. Read `docs/HeOCR_hocrgen_long_term_roadmap.md`
7. Read `docs/hocrgen_design_and_spec.md`
8. Read `src/hocrgen/cli.py`

`suggest-next` first 8:

1. Review PR #64 F3b
2. Review PR #63 F3a
3. Review commit `da1a1b6` F3b
4. Review commit `821c244` D2a
5. Review commit `b10c78d` E4a
6. Read `README.md`
7. Read `docs/HeOCR_hocrgen_long_term_roadmap.md`
8. Read provisional doc `tests/test_planning_docs.py`

Neither command explicitly identified `F4c` as the next implementation task.

**3. Compare To Expected**
Ideal top 5 should have been:

1. `F4c`: add deeper Hebrew rendering/provider metadata gates for hocrsyngen batches.
2. [.agent-plan.md](/Users/shaypalachy/clones/hocrgen/.agent-plan.md:20) and roadmap current critical path as primary authority.
3. [docs/HeOCR_hocrgen_long_term_roadmap.md](/Users/shaypalachy/clones/hocrgen/docs/HeOCR_hocrgen_long_term_roadmap.md:190) / [line 203](/Users/shaypalachy/clones/hocrgen/docs/HeOCR_hocrgen_long_term_roadmap.md:203) for F4c sequence.
4. README hocrsyngen/provider sections and [docs/synthetic_asset_contribution_guide.md](/Users/shaypalachy/clones/hocrgen/docs/synthetic_asset_contribution_guide.md:39).
5. Implementation surface: [src/hocrgen/fetchers/hocrsyngen_manifest.py](/Users/shaypalachy/clones/hocrgen/src/hocrgen/fetchers/hocrsyngen_manifest.py:29), [tests/test_hocrsyngen_manifest.py](/Users/shaypalachy/clones/hocrgen/tests/test_hocrsyngen_manifest.py:44), fixture manifest, source-health tests.

What it got right: F3b/F3a were recent and relevant; roadmap and README were high; maintenance state was labeled as maintenance; external spinout reviews are now more relevant than before.

What was wrong: it stopped at “review F3b” instead of inferring “F3b is complete, next is F4c”; `.agent-plan.md` ranked below README and historical spinout amendments; it did not surface `src/hocrgen/fetchers/hocrsyngen_manifest.py` or `tests/test_hocrsyngen_manifest.py` in the first-read list.

**4. Old Gaps**
- Work-first behavior: still weak. It produced review/history tasks, not the next work.
- Authority ranking: partially fixed, still wrong. Roadmap/README are high, but `.agent-plan.md` should outrank spinout amendments for current state.
- Provisional uncurated docs: useful and clearly labeled. `tests/test_planning_docs.py` was noisy but defensible.
- Maintenance separation: fixed enough. Queue/wiki/freshness stayed out of the main task list.
- Git/PR context: useful but over-dominant. It identified F3b/F3a, but did not use them to transition.
- `pr-summary --since main`: still useful, no regression. It correctly said no diff from main and warned local lint/health reports are not tied to HEAD.

**5. Current hocrgen Needs**
Splendor did not understand the F3b to F4c transition. It surfaced synthetic-provider/spinout context but not the actual implementation handoff: deeper Hebrew rendering/provider metadata gates around the hocrsyngen manifest path. It also missed the key files/tests for doing the work: `hocrsyngen_manifest.py`, `tests/test_hocrsyngen_manifest.py`, fixture `generation_manifest.json`, and source-health coverage.

**6. Smallest Reproducible Failures**
```bash
/tmp/splendor-v040/bin/splendor suggest-next "Resume hocrgen planning after F3b"
```
Failure: top item is “Review PR #64 F3b”; expected `F4c`. It displaced the explicit current task from `.agent-plan.md`.

```bash
/tmp/splendor-v040/bin/splendor brief --agent-context "Resume hocrgen planning after F3b"
```
Failure: “Files to read first” includes `src/hocrgen/cli.py` and config files, but omits `src/hocrgen/fetchers/hocrsyngen_manifest.py` and `tests/test_hocrsyngen_manifest.py`.

```bash
/tmp/splendor-v040/bin/splendor suggest-next "Resume hocrgen planning after F3b"
```
Ranking failure: historical `docs/2026_05_02_heocrsyn_spinout/...` authority scored above `.agent-plan.md`; current state should win.

**7. Recommendations**
Must fix before I would use it first:

1. Add completion-aware planning inference: if F3b is merged/current complete, use `.agent-plan.md` and roadmap “current critical path” language to propose the next unchecked notation, here `F4c`.
2. Promote current-state authority above historical amendments: `.agent-plan.md` plus roadmap current critical path must outrank outside/spinout reviews unless the query asks for historical review input.

Nice later:

1. Add implementation-surface discovery from roadmap terms: `F4c + hocrsyngen + manifest + tests` should pull `hocrsyngen_manifest.py`, fixture manifests, and matching tests.
2. Keep PR/git context, but demote merged PRs from “next action” to “background context” when the user asks to resume after that PR.
