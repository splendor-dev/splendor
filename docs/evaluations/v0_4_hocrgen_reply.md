Yes. The next Splendor slice should be “current-state planning inference.” Not maintenance.

1. Mostly parser/ranker first, schema later.

For hocrgen, a schema would be cleaner long term, but requiring explicit config before Splendor can read obvious current-state docs would miss the point. The repo already has strong planning language:

- `Last completed roadmap action`
- `next planned critical-path implementation should move to`
- unchecked task list rows
- roadmap status tables with `completed` / `planned`
- “Move next to `F4c`”

Splendor should parse those as high-confidence planning signals. That is not brittle regex if implemented as a layered extractor with evidence spans and confidence, not one-off string matching. It can detect common planning idioms, quote the source line internally, and only promote when multiple signals agree.

I’d add schema/config later as an override, not as the foundation. Something like `planning_authority: .agent-plan.md` and `roadmap_status_patterns` is useful for weird repos, but hocrgen should work without it because the current docs are explicit.

The behavior should be:

- If goal says “after F3b”, resolve `F3b` status from current authority.
- If `F3b` is completed and current authority says next is `F4c`, top work item becomes `Implement F4c...`.
- Merged PRs for F3b become “recent context to read if needed,” not actionable next steps.
- Historical docs can support why F4c exists, but cannot outrank current-state docs.

2. Implementation-surface discovery should use both roadmap/doc references and source search.

Roadmap/test references alone are too sparse. Broad source search alone is noisy. The right approach is a two-stage retrieval:

- Extract slice terms: `F4c`, `hocrsyngen`, `Hebrew rendering`, `provider metadata`, `manifest`, `generation_manifest`, maybe `synthetic`.
- Expand from authoritative text: docs and `.agent-plan.md` identify the domain and constraints.
- Search indexed paths/content for those terms.
- Rank by combined signals:
  - source/test role: `src/`, `tests/`, fixtures, config
  - exact token overlap: `hocrsyngen`, `manifest`
  - existing ownership boundary: fetcher/source adapter/test names
  - recent changed files from F4b, if available
  - negative weight for generic docs unless the question is planning-only

For F4c, the expected surfaced implementation set is obvious:

- `src/hocrgen/fetchers/hocrsyngen_manifest.py`
- `tests/test_hocrsyngen_manifest.py`
- `src/hocrgen/data/hocrsyngen/.../generation_manifest.json`
- source-health tests around hocrsyngen
- README / synthetic asset guide as policy references

So your P list is right, with one adjustment: merged PR demotion is part of P1, not P2. The failure mode is not just ranking polish; it directly caused the wrong handoff.
