**Verdict: no**

Splendor v0.5.2 is not useful again for hocrgen day-to-day handoff yet. It still leads with stale/merged-history-shaped work instead of the actual next slice.

**Evidence**

I installed the published wheel:

`uv tool install https://github.com/splendor-dev/splendor/releases/download/v0.5.2/splendor-0.5.2-py3-none-any.whl --force`

Confirmed: `splendor 0.5.2`.

Current hocrgen `main` is at `16144e0 F6f2a: Implement hocrsyngen evidence preflight reader (#78)`. Direct repo truth says:

- [.agent-plan.md](/Users/shaypalachy/clones/hocrgen/.agent-plan.md:8): last completed roadmap action is `F6f2a`.
- [.agent-plan.md](/Users/shaypalachy/clones/hocrgen/.agent-plan.md:152): next unchecked slice is `F6f2`.
- [.agent-plan.md](/Users/shaypalachy/clones/hocrgen/.agent-plan.md:153): `F6g` is also unchecked but gated after more evidence.
- [docs/HeOCR_hocrgen_long_term_roadmap.md](/Users/shaypalachy/clones/hocrgen/docs/HeOCR_hocrgen_long_term_roadmap.md:205): `F6f2` is planned and requires a settled hocrgen-owned import metadata form plus a larger validated hocrsyngen batch.
- `gh issue list` and `gh pr list` both returned `[]`.

Splendor output before refresh:

- `splendor brief --agent-context "continue the current hocrgen roadmap work"` led with `Continue F1c from current planning authority`.
- `splendor suggest-next "continue the current hocrgen roadmap work"` also ranked `Continue F1c` first.
- It then listed merged PRs: `#43`, `#70`, `#72`, `#45`.
- `splendor query "current hocrgen next planned slice"` returned a search result list, not an answer, and ranked `llms` first.

I then followed Splendor’s own safety flow for key authority docs:

- Previewed `splendor source refresh .agent-plan.md`
- Previewed `splendor source refresh docs/HeOCR_hocrgen_long_term_roadmap.md`
- Previewed `splendor source refresh docs/release_governance.md`
- Applied those three refreshes and ran `splendor ingest --pending --apply --json`

After that, Splendor still returned the same wrong handoff:

- `current_planned_work.slice_id` was still `F1c`.
- `actions[0].title` was still `Continue F1c from current planning authority`.
- It still promoted merged PR review links ahead of the actual unchecked `F6f2`.

I cleaned up the generated Splendor refresh artifacts afterward; the hocrgen worktree is clean.

**What It Got Useful**

It did surface some useful context:

- `docs/HeOCR_hocrgen_long_term_roadmap.md`
- `src/hocrgen/config/public_beta.yaml`
- benchmark reference config
- public-beta blocker language around larger hocrsyngen batch requirements

But that is not enough for handoff. The top recommendation is wrong, and the correct `.agent-plan.md` unchecked task list is not used as the primary source.

**Remaining Blockers**

- It treats an old F1c blocker sentence as the “current planned slice.”
- It does not distinguish “implemented but still blocks readiness” from “next work item.”
- It ranks merged PR history as actionable work.
- It does not prioritize `.agent-plan.md` active unchecked tasks over roadmap prose.
- Refresh/ingest does not retire or sufficiently demote superseded source summaries.
- `query` behaves like search, not answer synthesis, for the exact handoff question.

**Recommendations For Splendor**

1. Make `.agent-plan.md` unchecked task extraction a first-class handoff signal.
2. Penalize completed checklist items and merged PRs unless the user explicitly asks for history.
3. Parse roadmap status tables: `completed/current ref` must not become “next.”
4. Treat blocker prose as context, not a slice id, unless it maps to an unchecked planned item.
5. After source refresh, suppress superseded source versions from ranking.
6. Add a regression test using this hocrgen state: expected top answer is `F6f2`, with `F6g` gated behind it and required evidence.

I would not use Splendor for hocrgen handoff yet. Direct `rg` over `.agent-plan.md` plus `git log` and `gh pr/issue list` is still faster and more correct.
