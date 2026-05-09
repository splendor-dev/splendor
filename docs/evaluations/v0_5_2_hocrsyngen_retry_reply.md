**Verdict: maybe**

Splendor v0.5.2 is useful again for `brief` / `suggest-next`, but I would not trust `query` as a standalone handoff answer yet.

**Evidence**

Installed the published wheel:

```bash
uv tool install https://github.com/splendor-dev/splendor/releases/download/v0.5.2/splendor-0.5.2-py3-none-any.whl --force
splendor --version
# splendor 0.5.2
```

Current repo authority says:
- Active item: `S8b: Wet-test smoke run artifact generator`
- After S8b merges: next planned slice is `S8c` human-first static gallery
- Roadmap/production docs agree Phase S8 is current.

**Cold-Start Result**

Commands:

```bash
splendor brief --agent-context "continue the current hocrsyngen roadmap work"
splendor suggest-next "continue the current hocrsyngen roadmap work"
splendor query "current hocrsyngen next planned slice"
```

Important output:
- `brief` led with: `Continue S8b from current planning authority target=.agent-plan.md`
- `suggest-next` led with the same, with a good reason: `.agent-plan.md` identifies `S8b: Wet-test smoke run artifact generator`.
- It still listed stale merged PR review-history items immediately afterward: PRs `#39`, `#34`, `#45`, `#47`.
- `query` failed cold: `No matches found`.

Cold start answer: useful enough for handoff commands, not useful for query. It did not clearly say “run ingest” as the primary next step, but it did show provisional uncurated docs and curation commands.

**Applied-Ingest Result**

`ingest --pending --apply` initially said:

```text
No pending ingest jobs
```

I then followed Splendor’s own suggested source path:
- `splendor init`
- `splendor add-source .agent-plan.md`
- `splendor add-source docs/roadmap.md`
- `splendor add-source docs/production_readiness.md`
- `splendor add-source docs/wet_testing_program_plan.md`
- explicit `splendor ingest <source-id>` for each source

After that:
- `brief` still led with `Continue S8b from current planning authority`.
- `suggest-next` still led with `Continue S8b from current planning authority`.
- `query` improved from zero matches to seven matches, but did not directly answer the question. Its best match was `production readiness`, and `.agent-plan.md` was only match #4.
- Generated wiki state reported `contested=4`, apparently because `.agent-plan.md` is more current than broader planning docs. That is maintenance noise for day-to-day handoff.

`git status --short` was clean after the test.

**Remaining Blockers**

- `query "current hocrsyngen next planned slice"` still behaves like search, not answer synthesis. It should say “current active slice is S8b; next after merge is S8c.”
- Stale merged PRs are still too prominent. They are now lower priority, but still clutter the top handoff.
- The ingest path is awkward: cold start says sources are provisional, but `ingest --pending --apply` has no work until sources are manually added and `splendor init` has run.
- Applied ingest generates contested/review-needed maintenance state that looks scarier than it is.
- It does not reconcile actual git branch context against `.agent-plan.md`; it surfaces both, but a handoff tool should call out that mismatch explicitly.

**Recommendations For Splendor**

1. Make `brief` / `suggest-next` suppress merged PR review-history unless no current planning authority exists.
2. Make `query` produce a concise answer, not just ranked matches, when authority docs clearly contain the answer.
3. In cold start, when no sources exist, provide one explicit command sequence: `splendor init`, `splendor add-source ...`, `splendor ingest ...`.
4. Treat `.agent-plan.md` as higher freshness authority than roadmap/archive docs for “current work” questions.
5. Downgrade generated contradiction-review tasks when the “contradiction” is simply current-state doc versus broader roadmap history.

I would use Splendor again for `brief` and `suggest-next` in `hocrsyngen`, with manual verification against `.agent-plan.md`. I would not yet use `splendor query` as the handoff source of truth.
