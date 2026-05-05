# v0.2.0 SynthBanshee Evaluation Intake

## Purpose

This document records the sanitized post-`v0.2.0` external-agent evaluation that followed the
`v0.2.0` tag. The evaluator was a Claude Code agent working in a public companion project. The
private project-specific details are intentionally omitted because they are not needed to explain
the Splendor product findings.

The evaluation replaces the previous internal-only `M14-P3.1` source-lifecycle gate as the current
external workflow signal. Its conclusion is blunt: Splendor's core model is understandable and some
handoff surfaces are useful, but v0.2.0 is not ready as a daily-driver agent companion until source
registration hygiene, registry recovery, and validation correctness are fixed.

## Preserved Fixture

A sanitized fixture bundle was captured outside the repository:

- Local path: `/Users/shaypalachy/archive/splendor-fixtures/splendor-fixture-2026-05-05.tar.gz`
- SHA-256: `8b2fea5e3cd04c99d52d79398347ff7a38b41a30c410a3a1ab1985fbe63b162c`
- Contents: one representative run record, five source manifests, command output captures, and a
  `repo scan --json` preview

The fixture is not committed in this PR. It should be treated as a local regression source for the
v0.3 issues below. Do not publish raw project-specific details unless they have been sanitized.

## What Worked

- `brief --agent-context` produced a useful top-level handoff block with wiki status, source/run
  state, and recent source/run context.
- Curated topic pages contained real project value and surfaced recommendations that were not
  obvious from a git log alone.
- `splendor source update-path` repaired a renamed workspace source enough for the live manifest
  path/source ref to point at the new file.
- The source-refresh model was understandable: changed bytes create a new content-addressed source
  version, ingest writes a successor source-summary page, pruning can remove old generated state,
  and topic refs can migrate to the active version.

## Blocking Failures

### Historical repo-scan pollution

The evaluated workspace contained thousands of untracked source manifests produced by a historical
`repo_scan` run under Splendor `0.1.0a0`. Those manifests registered cache and local-agent files
such as `.mypy_cache/*` and `.claude/settings.local.json` as curated workspace sources.

The evaluator's v0.2.0 `repo scan --json` check suggests default documentation scans now honor
`.gitignore`, but `--all`, class-filtered scans, and `--apply` still need direct regression
coverage before this can be called fixed.

### No source-registry recovery command

Once a registry is polluted, v0.2.0 has no first-class cleanup command. Operators must manually
delete JSON manifests under `state/manifests/sources/`, which is not acceptable for an
agent-facing system.

### Duplicate canonical source refs

The fixture shows a source originally registered through `add-source`, later re-registered by repo
scan under a different source ID, and then refreshed into a third source ID. The refresh only
linked the repo-scan version to its successor. The original `add-source` manifest stayed active,
so lint correctly reported multiple active source versions for the same canonical source ref.

The missing primitive is a documented reconciliation path, such as `source supersede` or
`source reconcile`, plus scan behavior that does not create new active duplicates for already
curated canonical refs.

### Health false positives

`splendor health` reported `Run references unknown source_id` for run records whose `source_ids`
field exactly matched existing manifest filenames. Health must resolve run source IDs against the
manifest store directly and avoid duplicate provenance diagnostics for the same bad ref.

### Lint uses historical path fields as live paths

After `source update-path`, live `path` and `source_ref` fields pointed at the new file, but lint
still reported a missing old path from historical fields such as `original_path` or `logical_id`.
Historical registration identity should not make a deliberately repaired source fail the live
path-existence check.

## v0.3 Minimum Retry Bar

The same evaluator is willing to retry Splendor seriously on the companion project when these
v0.3 items land:

1. `repo scan`, including `--all`, class-filtered, and `--apply` paths, honors `.gitignore` and
   project-specific ignore rules.
2. `splendor source forget` supports safe single-source and bulk registry cleanup.
3. Duplicate canonical source versions can be reconciled through `source supersede`,
   `source reconcile`, or equivalent scan behavior.
4. Lint reads the live source model correctly after source refresh and path repair.
5. Health resolves source IDs against the manifest store without false unknown-source errors.

Lower-priority v0.3 polish includes standalone workspace maintenance actions, JSON output for
pending ingest drains, and easier release artifacts for trial installs.

## Roadmap Consequence

The next product direction is not broader synthesis, a mutating web UI, or advanced search. The
next track is v0.3 source hygiene and registry recovery. Public v1 work should start after the
v0.3 recovery loop is safe enough for another external trial.
