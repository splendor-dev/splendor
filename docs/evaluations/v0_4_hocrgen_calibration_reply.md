Here are three acceptance examples I would turn into tests.

**Example 1**
Goal string: `Resume hocrgen planning after F3b`

Expected top work item: `F4c: Add deeper Hebrew rendering/provider metadata gates for hocrsyngen batches`

Expected current-state authority:
- hocrgen `.agent-plan.md` line 8: last completed action is `F3b`
- hocrgen `.agent-plan.md` line 20: next critical-path implementation moves to `F4c`
- hocrgen `docs/HeOCR_hocrgen_long_term_roadmap.md` line 197: current critical path after `F3b`
- hocrgen `docs/HeOCR_hocrgen_long_term_roadmap.md` line 203: move next to `F4c`

Expected recent PR/git context placement: PR #64 / commit `da1a1b6` F3b should be background context under “recently completed / read for predecessor context,” not a work action.

Expected files/tests to read first:
- `.agent-plan.md`
- `docs/HeOCR_hocrgen_long_term_roadmap.md`
- `README.md`
- `docs/synthetic_asset_contribution_guide.md`
- `src/hocrgen/fetchers/hocrsyngen_manifest.py`
- `tests/test_hocrsyngen_manifest.py`
- `tests/test_source_ops.py`

Must not outrank top item: `Review PR #64: F3b...`

**Example 2**
Goal string: `Continue hocrgen roadmap work from current main`

Expected top work item: `F4c: Add deeper Hebrew rendering/provider metadata gates for hocrsyngen batches`

Expected current-state authority:
- `.agent-plan.md` current system state says last completed roadmap action is `F3b`
- `.agent-plan.md` active breakdown has `F4c` unchecked after completed `F4b`
- roadmap milestone table marks `F4b` completed and `F4c` planned after `F4b`
- roadmap current critical path says move next to `F4c`

Expected recent PR/git context placement: recent F3b/F3a commits should appear after the inferred next task as “recent merged context.” They should help explain why F3 is done, not become actions.

Expected files/tests to read first:
- `.agent-plan.md`
- `docs/HeOCR_hocrgen_long_term_roadmap.md`
- `README.md`
- `src/hocrgen/fetchers/hocrsyngen_manifest.py`
- `tests/test_hocrsyngen_manifest.py`
- `src/hocrgen/data/hocrsyngen/contracts/generation_manifest_v1/fixture-batch/generation_manifest.json`

Must not outrank top item: `splendor wiki status`, `source freshness`, or “review latest commit.”

**Example 3**
Goal string: `Start the next hocrsyngen provider-gate implementation work`

Expected top work item: `F4c: Add deeper Hebrew rendering/provider metadata gates for hocrsyngen batches`

Expected current-state authority:
- roadmap F4 table: `F4b` completed, `F4c` planned after `F4b`
- `.agent-plan.md`: `F4b` completed and `F4c` planned follow-up
- README hocrsyngen/provider section describing current manifest-backed source and missing deeper gates
- synthetic contribution guide allowing provider metadata and validation rules that improve Hebrew rendering/provenance/export checks

Expected recent PR/git context placement: F4b commit/PR context should be “predecessor implementation context.” Useful, but below the current `F4c` work item.

Expected files/tests to read first:
- `src/hocrgen/fetchers/hocrsyngen_manifest.py`
- `tests/test_hocrsyngen_manifest.py`
- `tests/test_source_ops.py`
- `README.md`
- `docs/synthetic_asset_contribution_guide.md`
- hocrsyngen fixture manifest under `src/hocrgen/data/hocrsyngen/...`

Must not outrank top item: historical spinout amendment docs or legacy `src/hocrgen/synthetic/generator.py` work. Those can be supporting context, not the handoff target.
