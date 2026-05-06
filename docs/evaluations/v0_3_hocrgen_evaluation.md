# Verdict

Splendor v0.3.0 is materially better on source lifecycle mechanics, but it is still not a high-leverage Codex companion for hocrgen planning. It now gets stale source state back to green with one obvious command, and `pr-summary --since main` is useful. But `brief`/`suggest-next` still do not beat direct reads for deciding actual hocrgen work; for this task, `rg` immediately found `F3b` as next while Splendor ranked stale outside-review summaries above the current roadmap.

I cleaned up all generated trial output afterward; the checkout is back clean on `main`.

# What I Tried

Real task: resume hocrgen planning after merged `F3a` and decide the next implementation task with current roadmap authority, invariants, tests, and stale outside-review constraints.

Install: GitHub Release wheel was attached at [`v0.3.0`](https://github.com/splendor-dev/splendor/releases/tag/v0.3.0). `uv` was not on PATH, and system `python3` was 3.9.6, so the first wheel install failed because Splendor requires Python `>=3.12`. I installed it in an isolated venv using `/opt/homebrew/bin/python3.12`; `splendor --version` returned `splendor 0.3.0`.

# Command Sequence

- `git status --short --branch`
- `curl -I -L https://github.com/splendor-dev/splendor/releases/download/v0.3.0/splendor-0.3.0-py3-none-any.whl`
- `/opt/homebrew/bin/python3.12 -m venv ...`
- `pip install https://github.com/splendor-dev/splendor/releases/download/v0.3.0/splendor-0.3.0-py3-none-any.whl`
- `splendor --version`
- GitHub MCP: recent merged PRs for `HeOCR/hocrgen`
- `splendor lint`
- `splendor health`
- `splendor source freshness`
- `splendor source list`
- `splendor workspace refresh --changed --ingest --rebuild-index --prune-superseded --update-topic-refs`
- `splendor lint`
- `splendor health`
- `splendor source freshness`
- `splendor ingest --pending --json`
- `splendor repo scan --json`
- `splendor repo scan --class documentation --json`
- `splendor brief --agent-context "..."`
- `splendor suggest-next "..."`
- `splendor pr-summary --since main`
- `splendor wiki status`
- `splendor task list`
- `splendor task list --generated-review`
- `splendor source reconcile .agent-plan.md --json`
- `splendor source forget <old-source-id> --json`
- `splendor source update-path <old-source-id> docs/nonexistent.md --json`
- Direct check: `rg -n "F3b|Current|critical|modern handwritten..." ...`

# Findings

- Refresh lifecycle is now much safer and more obvious. Baseline `health` failed with 23 checksum mismatches; the long refresh command fixed them all without manual cleanup.
- Yes, `workspace refresh --changed --ingest --rebuild-index --prune-superseded --update-topic-refs` left `lint` and `health` green.
- Stable logical IDs help: reports now show `Logical ID: source:<path>` and source refs, so the source lifecycle is understandable. But the primary artifacts still revolve around content-addressed `src-*` IDs, so reports remain visually noisy.
- Old source summaries were pruned and topic refs were updated. Old source manifests remain as historical records with `superseded_by`; old queue/run records remain unless explicitly forgotten.
- Generated churn is still too large: after one refresh, `git status` showed 152 changed paths, including 23 new manifests, 23 queue records, 23 run records, 46 source-summary add/delete entries, report files, wiki index/log changes, and topic ref edits. That is reviewable only with `pr-summary`, not as ordinary PR diff material.
- `source freshness` is genuinely useful. `source forget` preview is good and showed exactly three planned removals for an old source: queue record, run record, manifest. `source reconcile` was safe but no-op for `.agent-plan.md`. `source update-path` correctly refused to update a superseded source version.
- `lint` and `health` looked trustworthy in this run. They reported real stale checksum problems first, then went green after the advertised refresh.
- `brief --agent-context` was not an actionable Codex handoff. It did not say “F3b is next,” did not list the authoritative planning files, did not extract the relevant tests, and did not separate current roadmap authority from historical outside reviews. It suggested opening outside-review summaries first.
- Planning-authority ranking is still not strong enough. The current roadmap and `.agent-plan.md` clearly say F3b is next; Splendor’s brief/suggest-next ranked older outside-review docs above the roadmap.
- `suggest-next` was still generic. It suggested opening matched wiki pages and reviewing synthesis pages, not implementing `F3b` or reading the exact policy/test/doc files.
- `pr-summary --since main` is the best new feature I tried. It clearly explained refreshed vs superseded sources, generated source-summary churn, queue/run/report files, reviewer notes, and latest lint/health caveats.
- Splendor now beats grep/direct reads for source lifecycle diagnosis and PR explanation of generated-state churn. It does not beat grep/direct reads/git log for deciding hocrgen’s next planning or implementation step.
- Repo scan defaults are safer, but incomplete for this workflow: it found `CONTRIBUTING.md`, `docs/benchmark_ground_truth_guidelines.md`, and `docs/modern_handwritten_acquisition_policy.md` as documentation candidates, not curated sources. Those are important for the requested Codex handoff.
- `task list` and `task list --generated-review` produced no output, despite `wiki status` reporting 56 review-needed pages and 60 sources missing synthesis follow-up. That is confusing.
- Smallest repro for the main remaining failure:

```bash
splendor workspace refresh --changed --ingest --rebuild-index --prune-superseded --update-topic-refs
splendor lint
splendor health
splendor brief --agent-context "Resume hocrgen planning after F3a and decide the next implementation task"
splendor suggest-next "Resume hocrgen planning after F3a and decide the next implementation task"
rg -n "F3b|Current critical path|next planned" .agent-plan.md docs/HeOCR_hocrgen_long_term_roadmap.md README.md docs/modern_handwritten_acquisition_policy.md
````

Bluntly: v0.3.0 fixes the sharpest lifecycle breakage. It is now a maintained source-state system I can use without immediately fighting stale refs. It is not yet a reliable Codex companion for hocrgen planning, because the agent-critical answer still comes faster and more accurately from direct files and recent PR history.

```
```
