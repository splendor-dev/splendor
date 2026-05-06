# Splendor v0.4.0 Trial Prompt - SynthBanshee

Prompt for `claude@synthbanshee`.

```markdown
You are doing a follow-up trial of Splendor v0.4.0 in the SynthBanshee repo.

This is not a first trial. In the v0.3.0 trial, Splendor was useful for source
freshness, repo-scan safety, queue inspection, generated-review surfacing, and
some PR-summary behavior, but it failed the main handoff task because
`brief --agent-context` and `suggest-next` were effectively git-blind and let
maintenance/housekeeping outrank the real M17 ASR work.

Be blunt. The question is whether v0.4.0 is now good enough to use as a coding
agent handoff surface in SynthBanshee.

## Trial Goal

Evaluate this task:

> Pick up M17 ASR work after the effective-prosody cap landed; identify the next
> open work, the relevant files/policies, and what a coding agent should do next.

Do not implement the ASR follow-up. This is a Splendor evaluation and handoff
review, not a product-change request.

## Protect The Repo

Start by recording the current state:

```bash
git status --short --branch
git log --oneline --decorate -12
```

Use the explicit v0.4.0 Splendor binary if the project venv shadows it. The
previous trial hit this trap.

```bash
which splendor
splendor --version
~/.local/bin/splendor --version
```

Do not commit or push Splendor state changes. If a command mutates state during
exploration, record that fact and clean it up before ending.

## Current Ground Truth To Compare Against

You should verify this from local git/GitHub/repo inspection before judging
Splendor:

- PR #90 is merged: `fix(tts): #87 partial - effective-prosody cap addresses Whisper backdoor + helium range`.
- Local `main` should include commit `37c5f62`.
- PR #90 reduced the #87 Whisper backdoor failure but did not fully restore the
  `sp_it_a_0001` WER gap.
- The next open follow-up should be issue #91:
  `fix(tts): #87 follow-up - test rate-floor lift to address residual sp_it WER gap (R)`.
- The likely concrete work is to test raising `_EFFECTIVE_RATE_MIN` from `0.85`
  to `0.95`, while keeping PR #90's pitch cap unchanged.
- The key implementation/policy files are:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `docs/m17_phase_a_validation_report.md`
  - `docs/audio_generation_v3_design.md`
  - `synthbanshee/tts/renderer.py`
  - `synthbanshee/package/asr_sanity.py`
  - `tests/unit/test_effective_prosody_cap.py`
  - `tests/unit/test_asr_sanity.py`
  - `tests/unit/test_qa.py`

Important wrinkle: `.agent-plan.md` may contain older milestone state. A good
handoff should notice when recent GitHub/git authority supersedes stale planning
state rather than blindly telling an agent to do old work.

## Baseline Without Splendor

First answer the task using normal tools:

```bash
git status --short --branch
git log --oneline --decorate -12
gh pr view 90 --json number,title,state,mergedAt,url,body,labels,milestone
gh issue view 91 --json number,title,state,url,body,labels,milestone
rg -n "M17|ASR|Whisper|rate-floor|sp_it|effective-prosody|prosody cap|#91|#90|helium|backdoor" AGENTS.md CLAUDE.md README.md docs synthbanshee tests .agent-plan.md
```

Write the baseline handoff you would give without Splendor.

## Splendor Commands To Evaluate

Run these with Splendor v0.4.0:

```bash
splendor health
splendor lint
splendor queue inspect
splendor brief --agent-context "Pick up M17 ASR work after the effective-prosody cap landed"
splendor suggest-next "Pick up M17 ASR work after the effective-prosody cap landed"
splendor pr-summary --since main
```

If the repo has stale queue records, also inspect whether v0.4.0 exposes a
preview/apply cleanup path clearly:

```bash
splendor queue inspect --json
splendor queue clean --orphaned
splendor queue clean --superseded
```

Only use `--apply` if you intentionally want to test mutation behavior and can
cleanly restore the repo afterward.

## What To Judge

Please answer these directly:

1. Did `brief --agent-context` and `suggest-next` identify issue #91 as the next
   real work after PR #90, or did they get distracted by stale `.agent-plan.md`
   state, merged PR history, or maintenance?
2. Did Splendor surface the right policy constraints from `AGENTS.md`/`CLAUDE.md`
   around the ASR sanity check and paired listening test?
3. Did it name the right implementation and test files for the rate-floor
   follow-up?
4. Did maintenance remain discoverable without displacing the real work-first
   handoff?
5. Did the new queue cleanup surface fix the orphan/stale queue problem you saw
   in the v0.3 trial?
6. Is `pr-summary --since main` useful on this current state, and does it avoid
   misleading curated/generated classifications?
7. Would you now use Splendor first for a SynthBanshee handoff? If not, what is
   still missing?

## Report Format

Return:

- Verdict
- Commands run
- Baseline handoff without Splendor
- Splendor handoff summary
- Ground-truth match table
- Old v0.3 gaps: fixed / partially fixed / still broken
- Any state mutation or worktree churn
- Must-fix issues before another trial
- Nice-to-have improvements

Keep the critique concrete. Include smallest reproducible commands for each
failure.
```
