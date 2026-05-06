# Splendor v0.4.0 — SynthBanshee External-Retry Verdict

Install: `~/.local/bin/splendor` is now `0.4.0` (uv tool, sha256 verified `af5bccc378763d4e2c6df560df78a5cb98684e9c17c39a87b8d0ca382ad879f7`).
`.venv/bin/splendor` left at `0.2.0`.

## 1. Verdict

Yes — for SynthBanshee work I would now start with `splendor brief --agent-context` before `git log` / `gh issue list` / `rg`. v0.4.0 crossed the line. The git-blind gap is fixed: `brief` opens with the next ASR work-thread (#91) and the three commits that landed before it (#90/37c5f62, #82/94086a8, #77/2408757), authority docs (`AGENTS.md`, `docs/implementation_plan.md`), the right code/policy files (`asr_sanity.py`, `test_asr_sanity.py`, `m17_phase_a_validation_report.md`), and Splendor maintenance is now structurally below the work — not crowding it. The orphan-queue-payload gap from v0.3.0 is fully closed (`queue clean --orphaned` previews all 9 orphans, including the v0.3.0 reproducer `src-24d3518a…`, and exposes a clean JSON contract). It's not perfect — `brief` only surfaced one of four open ASR issues, missed `synthbanshee/tts/renderer.py` from "Files to read first" despite both `AGENTS.md` and `CLAUDE.md` calling it out by symbol name, and the four legacy mutate-immediately verbs (`ingest --pending`, `source refresh`, `source update-path`, `workspace refresh`) still have no `--apply` flag — but it's now the right first tool to run, with manual `gh issue list` and policy-file reads as a deliberate second pass, not a corrective one.

## 2. Actual top handoff

`brief --agent-context "pick up M17 ASR work"` — Suggested next (top 5):
1. `[high/work-thread]` Review issue #91 — `fix(tts): #87 follow-up rate-floor lift for residual sp_it WER gap (R)` ← `url=…/issues/91`
2. `[medium/git-context]` Review commit `37c5f62` — `#87 partial: effective-prosody cap (#90)`
3. `[medium/git-context]` Review commit `94086a8` — `#78 loudness contract + metadata trail (#82)`
4. `[medium/git-context]` Review commit `2408757` — `M17 Phase A validation (Whisper + UTMOS) (#77)`
5. `[medium/authority]` Read authority doc `AGENTS.md`

`suggest-next "pick up M17 ASR work"` (top 8): identical 1-5, then `CLAUDE.md` (provisional-uncurated, with `Curate:` hint), `docs/implementation_plan.md`, `wiki/topics/audio-quality-issues.md` (score 1).

Did either lead with the next open ASR issue? Yes — both put issue #91 first, with the `[high/work-thread]` tag separating it from the medium-priority git/authority context.

## 3. Compare to expected

Ideal top 5-8 (ground truth from the parallel `gh`/`git`/`rg` baseline):
1. issue #91 (rate-floor lift — immediate next)
2. issue #87 (parent thread: Whisper WER on I3+ Tier A — still open!)
3. issue #88 (`qa-report --asr` CI plan — open)
4. issue #92 (naturalness backlog from 2026-05-06 — open)
5. PR #90 / commit `37c5f62` (effective-prosody cap)
6. ASR sanity policy section in `AGENTS.md` (lines 89-102, 174-175)
7. `synthbanshee/tts/renderer.py` (`_apply_effective_prosody_cap`, `_EFFECTIVE_PITCH_*`, `_EFFECTIVE_RATE_*`)
8. `tests/unit/test_effective_prosody_cap.py` + `synthbanshee/package/asr_sanity.py` + `tests/unit/test_asr_sanity.py` + `docs/m17_phase_a_validation_report.md`

### What Splendor got right

- `#91` first as `[high/work-thread]` — exact match.
- Three correct git-context commits with sensible decay (`#90 → #82 → #77`).
- `AGENTS.md` as primary authority + `CLAUDE.md` correctly classified provisional-uncurated with curation command. `docs/implementation_plan.md` second.
- `docs/m17_phase_a_validation_report.md`, `synthbanshee/package/asr_sanity.py`, `tests/unit/test_asr_sanity.py`, `scripts/m17_phase_a_validation.py` in "Files to read first".
- Maintenance state clearly fenced: separate Splendor maintenance block + Maintenance commands + Maintenance notes. Wiki topic matches scored 1 vs commits scored 60-63 — token-similar matches genuinely demoted.
- `branch=main head=37c5f62 base=origin/main merge_base=…` git context block.

### What was wrong / missing / stale

- Issue surfacing too narrow. Recent issues and PRs listed only `#91`. Three other open ASR-relevant issues (`#87`, `#88`, `#92`) were missed entirely despite being labeled `comp: tts` and matching the goal terms. For a goal phrased `"pick up M17 ASR work"`, the parent issue `#87` — open, the literal anchor of `#91` — is a meaningful miss.
- `renderer.py` and `test_effective_prosody_cap.py` missing from "Files to read first". Both `AGENTS.md` line 174 and `CLAUDE.md` line 174 explicitly name `synthbanshee/tts/renderer.py` and `_EFFECTIVE_PITCH_*` / `_EFFECTIVE_RATE_*` as the don't-touch-without-Tier-3 surface. The cap test file is the unit-test floor named in the policy. Both should rank above `scripts/m17_phase_a_validation.py`.
- Two stale `Next actions` lines at the very bottom mix maintenance into work:
       - `Run splendor ingest --pending` to drain pending source ingests (drain verb!)
       - `Run splendor wiki suggest <source-id>`
  The top sections cleanly separated work from maintenance; the trailing `Next actions` undoes that separation.
- `pr-summary --since main` is degenerate on a clean `main` (`changed_paths: 0`, `head == merge_base`). Probe limitation, not a Splendor bug — but worth noting it's untested for branch-vs-main here. The `Latest local maintenance reports (not tied to current HEAD)` caveat is correctly worded.

## 4. Specific old-gap status

Gap: Git-aware handoff
v0.3.0: git-blind
v0.4.0: fixed
Notes: `brief` shows `head/base/merge_base` + 3 ranked commits + work-thread issue first

────────────────────────────────────────

Gap: Housekeeping demotion
v0.3.0: crowded out work
v0.4.0: fixed
Notes: Splendor maintenance block is structurally below work context; only the trailing `Next actions` mixes it back in

────────────────────────────────────────

Gap: Authority ranking (ASR policy + validation)
v0.3.0: mixed
v0.4.0: fixed
Notes: `AGENTS.md` (curated, score 156), `docs/implementation_plan.md` (score 141) above wiki/topic (score 1)

────────────────────────────────────────

Gap: Provisional uncurated docs
v0.3.0: invisible
v0.4.0: new + good
Notes: `CLAUDE.md`, `README.md`, `.agent-plan.md`, `docs/wet_testing_plan.md` all surface as provisional-uncurated with explicit `Curate:` command

────────────────────────────────────────

Gap: Queue cleanup (orphans)
v0.3.0: no path
v0.4.0: fixed
Notes: `queue clean --orphaned` previews all 9 orphans (including v0.3.0 reproducer `src-24d3518a…`); apply path is `--apply`; non-mutating without it (verified: residual file still on disk after preview run)

────────────────────────────────────────

Gap: Preview/apply consistency
v0.3.0: inconsistent
v0.4.0: partial
Notes: `queue clean` got the new contract. `ingest --pending`, `source refresh`, `source update-path`, `workspace refresh` still have NO `--apply` flag (verified via `--help`) — they remain mutate-on-call. Release notes claimed `"Reviewed mutating commands expose deterministic JSON mutation contracts"` — that was scoped to new commands, not legacy harmonization. Most acute risk: `ingest --pending` is still a drain verb with no preview gate.

────────────────────────────────────────

Gap: `pr-summary` cross-reference
v0.3.0: one-way
v0.4.0: untested
Notes: Trial `branch=main` with no diff; cannot exercise.

────────────────────────────────────────

Gap: JSON mutation contract
v0.3.0: absent
v0.4.0: fixed for new commands
Notes: `queue clean --orphaned --json` returns `{applied: false, selectors: [...], summary: {planned, written, skipped}, actions: [{job_id, path, source_id, cleanup_state, status, reason}, …]}`. Field names differ slightly from the release-note prose (`applied` vs `mode`, `mutates` not present) but the semantics are deterministic.

## 5. Current-task understanding (post-#90/#87)

- Did Splendor understand the post-#90 / #87 follow-up situation? Yes — issue #91 is correctly identified as the next thread, and `Reason: Spawned from` in `suggest-next` is wired to the parent (the body cuts off there but the work-thread ranking is right).
- Rate-floor / residual `sp_it` WER gap? Yes — issue #91's full title surfaces verbatim: `"test rate-floor lift to address residual sp_it WER gap (R)"`.
- ASR sanity policy + don't-touch-rendering-without-Tier-3 constraint? Partially. `synthbanshee/package/asr_sanity.py` and `tests/unit/test_asr_sanity.py` are in "Files to read first", and `AGENTS.md` is the top authority. But the actual `qa-report --asr` policy block inside `AGENTS.md` lines 89-102 and the don't-merge constraint at lines 174-175 are not directly cited — Splendor names the file but doesn't anchor to the policy section. For an agent that reads `AGENTS.md` end-to-end this is fine; for one that just scans the brief output, the constraint is one indirection away.
- Did it distinguish work vs Splendor's own state? Yes — `Splendor maintenance: sources=16 pages=20 queue_pending=1 review_needed=16` is its own labeled block, and the Maintenance notes explicitly say `"Wiki review-needed pages and missing synthesis are maintenance state, not default active human tasks."` Big improvement.

## 6. Smallest reproducible failures

### Failure 1 — open-issue surfacing is incomplete

```bash
~/.local/bin/splendor brief --agent-context "pick up M17 ASR work" | grep "issue #"
# Output: only #91

gh issue list --state open --search "ASR OR Whisper OR WER OR sp_it"
# Output: #87, #91, #88, #92 (four open ASR issues)
````

Missing items displaced by: nothing — there's just one slot under Recent issues and PRs. Parent issue #87 is the most defensible miss (it's the anchor #91 references).

### Failure 2 — `renderer.py` not in "Files to read first"

```bash
~/.local/bin/splendor brief --agent-context "pick up M17 ASR work" | sed -n '/Files to read first/,/Relevant matches/p'
#   - synthbanshee/package/asr_sanity.py
#   - tests/unit/test_asr_sanity.py
#   - docs/m17_phase_a_validation_report.md
#   - scripts/m17_phase_a_validation.py
#   - AGENTS.md

rg -l "_apply_effective_prosody_cap|_EFFECTIVE_PITCH_|_EFFECTIVE_RATE_" synthbanshee tests
# synthbanshee/tts/renderer.py
# tests/unit/test_effective_prosody_cap.py
```

The cap symbol `AGENTS.md` / `CLAUDE.md` call out by name lives in two files that don't appear in the list.

### Failure 3 — apply-gate not harmonized

```bash
~/.local/bin/splendor ingest --help | grep -E "apply|pending"
#   --pending   Drain pending ingestion jobs from the queue.
# (no --apply, no --plan, no --dry-run)
```

Same shape for `source refresh`, `source update-path`, `workspace refresh`. The `queue clean` contract was applied to new commands only.

## 7. Recommendations

Must fix before next trial (blockers):

1. Harmonize `--apply` across the four legacy mutating verbs: `ingest --pending`, `source refresh`, `source update-path`, `workspace refresh`. Either add `--apply` (preview-by-default) or rename the destructive form (e.g. `ingest drain`). Right now the surface is half-modernized: `queue clean` previews safely, `ingest --pending` drains immediately. An agent that internalized "v0.4.0 commands are preview-by-default" can still mutate manifests with `ingest --pending --json`. This is the same trap that bit the v0.3.0 trial.
2. Surface ≥3-5 work-relevant open issues in `brief` / `suggest-next`, not just the highest-scoring one. `comp: tts` + goal-keyword matches are abundant (#87, #88, #92 here). A single-issue ceiling makes `brief` a worse first stop than `gh issue list` whenever there are multiple parallel threads.

Nice but later:

3. Add `synthbanshee/tts/renderer.py` (and any file referenced by `_EFFECTIVE_*` symbols inside curated authority docs) to "Files to read first" via a "policy-doc-cited path" boost.
4. Drop the trailing maintenance lines in `brief`'s "Next actions" footer — keep maintenance in its own block as v0.4.0 already does at the top.
5. Anchor cited authority sections (e.g. `AGENTS.md#asr-sanity-check-policy`, `AGENTS.md#what-not-to-do`) instead of just the file path, when the policy block is the actionable piece.
6. Make `pr-summary --since main` recognize the `head == merge_base` case and emit `(no diff vs <ref>)` more loudly than the current `Changed paths: 0` line.
7. Tighten the JSON contract field names to the release-note prose (`mode`, `mutates`) for grep-friendliness.

---

## What I did NOT do

Per privacy default — no upstream issues filed, no public writeup drafted. Wheel install was scoped to `~/.local/bin/splendor` via uv tool; `.venv/bin/splendor` untouched. No `splendor … --apply` invoked anywhere; queue is unchanged (9 orphans still on disk). Forensic-fixture decision deferred to you (q3 from prior message).

Standing by for direction on (a) whether to memo-update the v0.3.0/v0.4.0 splendor memory, (b) whether to publish, (c) whether to bundle a v0.4.0 forensic fixture.
