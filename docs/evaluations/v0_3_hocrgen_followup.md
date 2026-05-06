# Splendor hocrgen Trial Feedback

## 1. Ideal top 5 `brief --agent-context` items

1. `.agent-plan.md` → `## Current System State`
       - Expected first because it explicitly says last completed action is `F3a`, `F3` remains partial, and next critical-path implementation should be `F3b`.

2. `docs/HeOCR_hocrgen_long_term_roadmap.md` → `## 4.3 Current critical path` and F3 milestone table
       - This names `F3b` as planned after `F3a` and explains why F4/F5 are follow-ons.

3. `docs/modern_handwritten_acquisition_policy.md`
       - This is the policy contract F3b must implement: consent, release terms, privacy screening, takedown/removal, scan metadata, composition metadata, typed intake manifest.

4. `README.md` → modern handwriting / roadmap / “what is next” sections
       - Especially the current capability summary and the line saying F3b should add the typed repo-tracked operator intake manifest before collecting samples.

5. `tests/test_planning_docs.py`
       - This is the regression surface that encodes current/next notation consistency, including assertions around `F3a`, `F3b`, the policy boundary, and required roadmap language.

Expected PR context: `HeOCR/hocrgen#63`, “F3a: Define rights-clean modern handwritten acquisition policy.” I would also expect recent merged PRs only as supporting history, below the current files.

## 2. Incorrect ranking behavior observed

Splendor ranked these above or alongside the roadmap:

```text
Suggested next:
- [medium/goal-match] Open goal match wiki/sources/src-e41e11ee9c19a651f285b6ec36b0652f853bf66e730eb221c0f7afd315681103.md
- [medium/goal-match] Open goal match wiki/sources/src-2c57b11eadfa441b2c3498778253f09afe86d42de25c257398774b97983a7abb.md
- [medium/goal-match] Open goal match wiki/sources/src-2a426a9848b5f52dbe77701d7ee18f5c515f3d6093ed8f18c0b02c8cb8ce8e13.md
```

Those were:

* `docs/2026_05_01_outside_review/chatgpt_review.md`
* `docs/HeOCR_hocrgen_long_term_roadmap.md`
* `docs/2026_05_01_outside_review/gemini_review.md`

The problem was not that outside reviews appeared at all; it was that stale/historical review summaries appeared before `.agent-plan.md`, `modern_handwritten_acquisition_policy.md`, and the tests that actually constrain the next task.

## 3. Authority heuristics expectations

I would not hard-code `.agent-plan.md` and roadmap as always-current globally.

I would make this configurable in `splendor.yaml`, but give repo-root `.agent-plan.md`, `AGENTS.md`, `README.md`, and files matching `docs/*roadmap*.md` strong default authority heuristics when no explicit config exists.

Best model:

* configured authority wins
* default heuristics are a useful fallback with labels like `inferred-authority`

## 4. Uncurated documentation expectations

`brief` should report important uncurated docs and may use them as context, but it must label them clearly as uncurated.

For hocrgen, omitting:

* `CONTRIBUTING.md`
* `docs/benchmark_ground_truth_guidelines.md`
* `docs/modern_handwritten_acquisition_policy.md`

made the handoff incomplete.

Preferred presentation:

* “Authoritative curated sources”
* “Important uncurated repo docs detected”
* “Used as provisional context; run `splendor repo scan --class documentation --ingest ...` to curate”

## 5. PR churn concerns

The churn becomes acceptable with a combination of:

* fewer committed generated files
* moving queue/run/report state out of normal PR review by default
* clearer reviewer-significant grouping
* compact mode

`pr-summary` helped, but 152 paths is still too much.

Queue records, run records, timestamped lint/health reports, and source-summary add/delete churn should not dominate a planning PR unless they are the actual subject.

## 6. Review-needed task discoverability

I expected review-needed / missing-synthesis items to appear as tasks, or for `task list` to explain why it is empty and point to the right command.

Either of these would be fine:

```bash
splendor task list --wiki-review
splendor wiki status --review-needed
```

But silent empty output while `wiki status` says `review_needed=56` is confusing.

## 7. Highest-priority fixes

If only two fixes before the next hocrgen trial:

1. git-aware/work-first `brief`
2. stronger authority ranking for roadmap and `.agent-plan.md`

Generated churn is important, but the companion value depends first on answering the work question correctly.

## 8. Smallest hocrgen acceptance test

```bash
splendor brief --agent-context "Resume hocrgen planning after F3a"
```

Should return, in the first screen:

1. Next task: `F3b` implement bounded modern handwritten acquisition workflow and typed intake manifests.
2. Primary authority: `.agent-plan.md` current state.
3. Primary roadmap: `docs/HeOCR_hocrgen_long_term_roadmap.md`, current critical path / F3 table.
4. Policy contract: `docs/modern_handwritten_acquisition_policy.md`.
5. Supporting user docs: `README.md` and `CONTRIBUTING.md`.
6. Regression surface: `tests/test_planning_docs.py`.
7. Recent merged context: PR `#63` / `F3a`.
8. Explicit warning: outside reviews are historical/contextual and must not outrank current roadmap state.
