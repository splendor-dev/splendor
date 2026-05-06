# Splendor v0.4.0 Trial Prompt - hocrsyngen

Prompt for `codex@hocrsyngen`.

```markdown
You are doing a first-time trial of Splendor v0.4.0 in `hocrsyngen`.

You have never used Splendor before. Treat that as part of the evaluation: I
want to know whether Splendor is discoverable and useful from a cold start, not
whether you can guess its intended workflow.

## What Splendor Is

Splendor is a local-first, git-native knowledge compiler and agent handoff tool.
It is supposed to help coding agents understand current repo state, roadmap
state, PR context, and next work without replacing direct code/docs inspection.

This repo has not historically used Splendor, so expect no existing Splendor
workspace state unless someone already initialized it.

## Trial Goal

Evaluate whether Splendor can help a new agent understand and review the current
`hocrsyngen` work:

> Review the current S4c condition-control bundle branch/PR, identify whether
> the handoff is coherent, and say what the next roadmap work should be after
> S4c.

Do not implement product changes unless you find an urgent local issue. This is
primarily a Splendor adoption/review trial.

## Protect The Repo

Start by recording the current git state. If you initialize Splendor or run
mutating commands, do it on a throwaway branch or worktree so the active PR
branch is not polluted.

Recommended:

```bash
git status --short --branch
git log --oneline --decorate -12
git switch -c trial/splendor-v0.4-first-pass
```

Do not commit or push Splendor trial state unless explicitly asked.

## Current Ground Truth To Compare Against

You should be able to discover these facts from normal repo inspection, and
ideally Splendor should help surface them:

- Current branch: `feature/s4c-condition-control-bundles`
- Active PR: `#37`
- Active roadmap item: `S4c: Condition control bundles`
- Last completed roadmap/PR: `S4b: Add deterministic style parameter bundles`,
  PR `#36`
- Current phase: Phase S4, Persona/Style/Condition Controls
- Likely next roadmap item after S4c: `S4d: Style consistency checks`
- Important files:
  - `.agent-plan.md`
  - `AGENTS.md`
  - `README.md`
  - `docs/roadmap.md`
  - `docs/generation_manifest_v1.md`
  - `docs/hocrgen_integration.md`
  - `docs/decisions/0005-persona-style-condition-semantics.md`
  - `src/hocrsyngen/generator.py`
  - `src/hocrsyngen/cli.py`
  - `src/hocrsyngen/validation.py`
  - `tests/test_generation.py`
  - `tests/test_cli.py`

A good handoff should prioritize S4c review/closure and then S4d. It should not
bury that under generic maintenance, stale history, or broad repo scanning
noise.

## Baseline Without Splendor

First, establish what a normal agent would see:

```bash
git status --short --branch
git diff --stat main...HEAD
git log --oneline --decorate -12
rg -n "S4c|S4d|condition|controls.condition|condition bundle|style consistency|Phase S4" .agent-plan.md README.md docs src tests
```

Briefly note the baseline answer you would give without Splendor.

## Splendor Cold Start

Use Splendor v0.4.0. If it is not installed, install it however your
environment normally installs CLI tools, preferably from the `v0.4.0`
release/tag. Record any installation friction.

Run:

```bash
splendor --version
splendor --help
splendor init
splendor health
```

Then try to discover the repo without assuming prior Splendor knowledge:

```bash
splendor repo scan --class documentation --json
splendor repo scan --class configuration --json
splendor repo scan --class code --json
```

Evaluate whether the scan results point to the right files or produce too much
noise.

If you need to seed a useful minimal workspace, register only the core handoff
sources:

```bash
splendor add-source AGENTS.md --capture-source-commit
splendor add-source .agent-plan.md --capture-source-commit
splendor add-source README.md --capture-source-commit
splendor add-source docs/roadmap.md --capture-source-commit
splendor add-source docs/generation_manifest_v1.md --capture-source-commit
splendor add-source docs/hocrgen_integration.md --capture-source-commit
splendor add-source docs/decisions/0005-persona-style-condition-semantics.md --capture-source-commit
splendor add-source src/hocrsyngen/generator.py --capture-source-commit
splendor add-source src/hocrsyngen/cli.py --capture-source-commit
splendor add-source src/hocrsyngen/validation.py --capture-source-commit
splendor add-source tests/test_generation.py --capture-source-commit
splendor add-source tests/test_cli.py --capture-source-commit
splendor ingest --pending
```

Then run:

```bash
splendor brief --agent-context "Review the current S4c condition-control bundle branch and identify remaining PR handoff work"
splendor suggest-next "Continue hocrsyngen roadmap work after S4c"
splendor pr-summary --since main
splendor queue inspect
splendor lint
```

If a command fails, keep going and report the exact failure.

## What To Review

Please answer these directly:

1. Would you use Splendor again in `hocrsyngen` after this first trial? Why or
   why not?
2. Was cold-start setup obvious enough for a repo that had never used Splendor?
3. Did Splendor correctly surface the current S4c branch/PR and the S4d next
   step?
4. Did it understand `.agent-plan.md` as current dynamic state rather than
   treating roadmap history as equally current?
5. Did it help with PR review, or was direct `git diff`/`rg` still better?
6. Did generated Splendor state or queue/maintenance output create confusing
   repo noise?
7. Did `brief --agent-context` and `suggest-next` keep actual work ahead of
   maintenance?
8. What are the top two Splendor fixes needed before you would recommend adding
   it to this repo?

## Report Format

Return:

- Verdict
- Commands run
- Baseline answer without Splendor
- Splendor answer/handoff summary
- Ground-truth match table
- First-use friction
- State/worktree churn observed
- Must-fix issues
- Nice-to-have improvements

Be blunt. The useful feedback is where Splendor failed, confused you, or
required too much ceremony.
```
