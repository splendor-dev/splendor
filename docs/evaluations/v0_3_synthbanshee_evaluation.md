# Splendor v0.3.0 trial — SynthBanshee, 2026-05-06

## 1. Real task attempted

"Pick up M17 ASR regression work after PR #87 effective-prosody cap landed; identify the next milestone and what's still open." A planning question that spans `docs/spec.md`, `docs/audio_generation_v3_design.md`, `docs/implementation_plan.md`, recent PRs (#87, #86, #85, #82), and `CLAUDE.md`'s ASR-sanity-check policy — exactly the spanning kind of query `brief`/`suggest-next` claim to handle.

## 2. Install

Installed the v0.3.0 wheel from GH release (`splendor-0.3.0-py3-none-any.whl`, sha256 `32a3d5f9b19e2baf96d98ada0750ab8de7ffef359a3467d3709db8fae6341ce2`) via `uv tool install <release-wheel-url>`. Resolved 19 packages, installed in 4 ms. #120 ✓ — the release artifact installs the way the release notes promise.

PATH trap caught: `which splendor` resolves to `/Users/shaypalachy/clones/SynthBanshee/.venv/bin/splendor` (still v0.2.0 — the leftover from the previous trial). Used `~/.local/bin/splendor` (the uv-tool 0.3.0 binary) explicitly throughout. Project venv was deliberately not bumped.

## 3. Commands run, in order

```bash
~/.local/bin/splendor --version          # 0.3.0
~/.local/bin/splendor lint               # baseline: 2 issues
~/.local/bin/splendor health             # baseline: 96 issues
~/.local/bin/splendor source forget --help
~/.local/bin/splendor source reconcile --help
~/.local/bin/splendor source --help
~/.local/bin/splendor queue --help
~/.local/bin/splendor ingest --help
~/.local/bin/splendor queue inspect --json    # 23 done / 1 failed / 1 pending
~/.local/bin/splendor ingest --pending --json # ⚠ mutated state
~/.local/bin/splendor repo scan --help
~/.local/bin/splendor repo scan --json        # default = documentation, 28 candidates
~/.local/bin/splendor repo scan --all --json  # 194 candidates, 0 in killer dirs
~/.local/bin/splendor brief --agent-context "<task>"
~/.local/bin/splendor suggest-next "<task>"
~/.local/bin/splendor pr-summary --since main
~/.local/bin/splendor pr-summary --since HEAD~5
~/.local/bin/splendor task list                       # empty (correct)
~/.local/bin/splendor task list --generated-review    # 7 contradiction-review tasks
~/.local/bin/splendor source freshness
~/.local/bin/splendor source forget --matching 'src-24d3518a*'   # ⚠ orphan-queue gap
~/.local/bin/splendor source forget src-24d3518a...              # ⚠ Unknown source ID
~/.local/bin/splendor source forget src-7ab4089c...              # works on registered source
~/.local/bin/splendor source list
~/.local/bin/splendor queue retry --help
~/.local/bin/splendor source update-path --help
~/.local/bin/splendor source update-path configs/taxonomy.yaml synthbanshee/data/taxonomy.yaml --json
~/.local/bin/splendor lint                # → 1 issue (live-path cleared, provenance still flagged)
~/.local/bin/splendor source freshness    # missing=1 → 0
~/.local/bin/splendor workspace refresh --help
git checkout -- state/                    # revert mutations
~/.local/bin/splendor lint                # -> back to 2 (clean)
```

## 4. repo scan safety — yes, fixed

`--all` returned 194 candidates from 194 scanned (27 ignored, 54 unsupported) — 0 under `.mypy_cache/`, `.venv/`, `__pycache__/`, `.git/`, `.claude/`, `node_modules/`, `dist/`, `build/`, `htmlcov/`. The 2 candidates with `data/` in the path are `synthbanshee/data/__init__.py` and `synthbanshee/data/taxonomy.yaml` — canonical package data, not the gitignored output dir. Defaults to `--class documentation` when no class flag is given. `--apply` requires `--class` or `--all`. Large candidate sets gated behind `--allow-large-apply`. #111 verified empirically.

## 5. .gitignore / .splendorignore — .gitignore confirmed; .splendorignore not exercised

`ignored_paths` reasons split between `gitignore` (9) and `managed_or_transient` (18, the built-in defaults). I did not create a `.splendorignore` to stress-test the override, since the failure mode that burned us before was the absent-.splendorignore default — and that case is now safe.

## 6. source forget — works on registered sources, has a real edge case

Preview-by-default with `--apply`. On a real registered source it lists planned mutations (queue record, source manifest, summary page, index entry), skipped items (run records still referenced by other state), and residual references (planning text, wiki text). That's first-class diagnostic surface. #109 ✓ for the common case.

Edge case that's not covered: SynthBanshee has 9 dangling `state/queue/ingest-src-*.json` files whose source manifest no longer exists on disk (`lint` flags them as "Queue payload is missing source manifest"). `source forget` cannot clean these because:

* `source forget --matching 'src-24d3518a*'` → "No matching sources" (glob matches against the registry, not files on disk)
* `source forget src-24d3518a...` → `Error: Unknown source ID`

The only documented way to clean them is `rm state/queue/ingest-src-*.json` — exactly the manual-deletion footgun #109 was supposed to remove. Worth a follow-up upstream issue.

## 7. source reconcile — present, not exercised

Preview-by-default with `--apply` and `--current` to pick the keeper. Help text is sensible. No duplicate-active scenario was present in the curated registry to exercise it against, so I have surface-level evidence only.

## 8. Moved/changed sources — repaired cleanly

`source update-path configs/taxonomy.yaml synthbanshee/data/taxonomy.yaml --json` returned a clean structured response:

* `status: repaired`
* both old and new paths preserved as aliases
* checksum matched after move
* `next_commands: ["splendor ingest --pending", "splendor source freshness"]`

After the repair, `lint` dropped from 2 issues → 1 and `source freshness` flipped `missing=1 → 0`. #113 verified.

## 9. health and lint — diagnostics are real, not phantom

* `health` reports 96 issues against the actual SynthBanshee state. All are genuine drift (curated sources whose live files moved/changed since last ingest). Hints route to the right next command. #112 ✓.
* `lint` correctly distinguishes "live source path missing" (real broken state) from "provenance path missing" (historical metadata). #113 ✓.
* Minor nit: after a successful `update-path`, `lint` still flags "Provenance path does not exist" for the old location even though splendor itself just performed the repair. That's noise after a self-induced repair; in steady state it's defensible (audit trail of where the source came from), but for an agent-driven workflow it adds an item that no command will ever close.

## 10. workspace refresh flag combo — understandable, but mutating with no preview

Each of `--changed`, `--ingest`, `--rebuild-index`, `--prune-superseded`, `--update-topic-refs` has a clear single purpose in the help text. They compose, and they're opt-in (no `--all` shortcut, which is good — avoids implicit batch). I did not run the full chain because there is no `--apply` gate: it mutates immediately. That's inconsistent with `source forget` / `source reconcile` (which preview by default) and with the spirit of #121.

## 11. Pending ingest / queue state — JSON output is solid

`queue inspect --json` returns `{total, status_counts, items[]}` with full job metadata (`id`, `type`, `status`, `attempts`, `payload_ref`, `last_error`, `source_id`, `operator_state`, `record_path`).

`ingest --pending --json` returns `{total, summary{processed,succeeded,failed,skipped}, items[]}`.

Both are agent-handoff-ready. #122 ✓ — with one caveat (next item).

Footgun on the way: `ingest --pending --json` is a drain verb, not a preview, and there's no `--apply` flag. Calling it during exploration mutated one source manifest. Documented behavior, but inconsistent with the rest of v0.3 and easy for an agent to misread.

## 12. brief --agent-context — partial; still not actionable

Output structure is good (`Goal / Suggested next / Wiki status / Relevant matches / Recent sources / Recent runs / Last query / Next actions`, ~6 KB). Wiki-topic matches surfaced sensibly for the ASR query:

* `ssml-prosody-parameters.md`
* `audio-quality-issues.md`
* `preprocessing-pipeline.md`

But the actionable parts fail in two specific ways:

* `Suggested-next` is dominated by splendor housekeeping — the top 5 items are source refresh + queue inspect, not work on the M17 ASR question. Wiki matches start at item #6.
* `brief` is git-blind. PRs #87/#86/#85/#82 (the entire authority for the M17 work I asked about) do not appear anywhere — not in "Suggested next", not in "Relevant matches", not in "Recent runs" (which lists splendor's own ingest runs). For a coding-agent picking up a feature branch or recent work, that's a major blind spot.

Net: for SynthBanshee planning/authority handoff, `git log --oneline --stat HEAD~10..HEAD` plus reading recent PR descriptions is still strictly better than `brief --agent-context`. The #115/#116 promise is partially fulfilled — token-similar matches are deprioritized — but the housekeeping noise crowds out task-relevant authority, and git history is invisible.

## 13. suggest-next — same shape as brief's next list

Same housekeeping-dominates-goal-match issue. Top 5 are:

* source refresh × 3
* queue inspect × 2

Real and useful, but not what a coding agent is looking for.

Score 67 for `audio-quality-issues.md` (the older 7500 Hz lowpass investigation) outranks score 35 for `ssml-prosody-parameters.md` (more directly relevant to prosody-cap work) — token similarity is winning over semantic relevance.

The summary header (`changed_sources=14 missing_sources=1 queue=25 review_needed=16 contested=7 stale=0`) is genuinely useful as triage signal, though.

## 14. Generated contradiction-review tasks — out of the way by default

`task list` (default) is empty.

`task list --generated-review` shows 7 contradiction-review tasks.

`--include-generated-review` lets them be merged into the default list.

The contradiction evidence stays discoverable, the noise stays gated. #117 ✓ — clean.

## 15. pr-summary --since main — useful when there's a branch to summarize

On `main` itself it's degenerate (1 changed path, only because of an unrelated state mutation).

With `--since HEAD~5` it correctly enumerated 30 changed files across the recent #87/#86/#85/#82 work and warned that local lint/health reports are not tied to the current HEAD.

One real miss:

* `synthbanshee/tts/renderer.py`
* `docs/spec.md`
* `synthbanshee/augment/preprocessing.py`
* etc.

All curated sources — landed under "Other changed paths" instead of "Curated sources", because the manifest hadn't been refreshed for those files.

The cross-reference is one-way (`manifest-was-modified → "Curated"`), missing the reverse (`file-is-curated → "Curated"`).

## 16. Where Splendor beat grep / direct reads / git log

* `source freshness`: per-source manifest-checksum vs current-checksum diff in one screen, with the right next command. Faster than `git diff` + manually mapping changed files to curated knowledge.
* `queue inspect --json` failed/pending filter (with a small `jq`/python pass): pinpoints the broken state. Cleaner than crawling `state/queue/`.
* `task list --generated-review`: instantly tells you which contradiction reviews are open without grepping the filesystem.
* `source forget` preview: surfaces residual references that a manual `rm` would silently leave dangling — that's a real win.

## 17. Where Splendor still slowed me down or confused me

* PATH trap with the SynthBanshee `.venv` shadowing the uv-tool 0.3.0 install. Saved a few minutes of wrong-version output by checking `which splendor` immediately, but that's a recurring trip hazard until the project venv is bumped.
* `brief --agent-context` told me about source-freshness drift before telling me anything about the actual work I was picking up. For "resume after recent docs/code changes" workflows, that drowns out the signal.
* `ingest --pending --json` is a drain verb without an `--apply` gate. Inconsistent with `source forget`/`source reconcile`. I lost the "exploratory probe" property by calling it.
* Apply-gate inconsistency generally:
  - `source forget` and `source reconcile` are preview-by-default
  - `source update-path`, `source refresh`, `ingest --pending`, `workspace refresh` all mutate immediately
  - An agent expecting uniform `--apply` semantics will get burned at least once.
* Orphan queue payloads (9 in this repo) have no documented cleanup path other than manual `rm`.

## 18. Smallest reproducible failure (orphan queue cleanup gap)

```bash
~/.local/bin/splendor source forget --matching 'src-24d3518a*'
# → "No matching sources." (queue payload exists, source manifest does not)

~/.local/bin/splendor source forget src-24d3518af53608a9aa7efb59e393d0c93cc7d67c9a302058f21fe57dc4808b56
# → "Error: Unknown source ID"

ls state/queue/ingest-src-24d3518a*.json
# file is still there; only `rm` removes it
```

---

# Bottom-line verdict

v0.3.0 is materially better than v0.2.0.

The five v0.2 blockers are fixed empirically:

* repo-scan ignore safety, including `--all`, class-filtered, and apply paths
* safe `splendor source forget` cleanup for registered sources
* source lifecycle refresh and changed-source workflow understandability
* live-source lint/path repair behavior after refresh and path updates
* pending-ingest JSON output plus release artifacts for trial installs

#117 is clean. #120, #122 land. The repo-scan pollution mode that started this whole thread is gone — fresh checkouts won't get blanketed in `.mypy_cache/*` manifests anymore.

It is still not daily-driver-ready as a Claude Code companion for SynthBanshee.

The reason is narrower than in v0.2.0: the core handoff promise (`brief --agent-context` returning actionable, git-aware, authority-ranked context) is not delivered.

Splendor is git-blind, so it can't see PRs, branches, or recent commits — which is where the authoritative state of an active milestone actually lives. Until `brief` either consumes git history or `suggest-next` ranks task-relevant authority above splendor's own state-maintenance queue, a coding agent picking up real work will still reach for `git log` and direct reads first.

Recommended use today:

* source-freshness drift detection
* repo-scan hygiene previews (now safe)
* `pr-summary` file-level diff classification
* contradiction-review surface (kept out of the way)
* `source forget`/`update-path` for clean source lifecycle

Recommended against today:

* treating `brief --agent-context` as the primary handoff for a fresh agent session

Open issues to file upstream:

* (a) orphan queue payload cleanup gap
* (b) `ingest --pending` and `workspace refresh` lack `--apply` gates while peer commands have them
* (c) `brief`/`suggest-next` housekeeping outranks goal-matched authority
* (d) `brief` is git-blind
* (e) `pr-summary` doesn't classify changed paths against the curated registry in reverse
* (f) post-`update-path` provenance lint nit

Working tree is clean. No code or curated state was committed; one transient state mutation from `ingest --pending --json` was reverted with `git checkout -- state/`.
