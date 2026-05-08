# Splendor CLI Overview

This guide summarizes the main CLI surfaces. It is intentionally higher level than the product spec
and lower level than the root README.

## Workspace Setup

```bash
splendor init
splendor lint
splendor health
splendor serve
```

- `init` creates the local Splendor workspace layout.
- `lint` validates linked wiki, planning, source, queue, and run state.
- `health` reports operational state and repair guidance.
- `serve` starts the read-only local browser UI.

## Source Discovery And Curation

```bash
splendor repo scan --class documentation
splendor repo scan --class code
splendor repo scan --apply --class documentation
splendor add-source README.md --capture-source-commit
splendor add-source --glob "docs/**/*.md"
splendor add-source --dir docs
```

Source discovery and source curation are separate. `repo scan` previews candidates by default and
does not register sources unless `--apply` is used with a class filter or `--all`.

## Source Lookup And Freshness

```bash
splendor source list
splendor source lookup roadmap
splendor source freshness
splendor source refresh README.md
splendor source refresh README.md --apply
splendor source update-path README.md docs/README.md
splendor source update-path README.md docs/README.md --apply
```

`source freshness` is non-mutating and reports checksum drift for curated workspace-backed sources.
Refresh and path-update commands preview planned writes first; add `--apply` after review.

## Registry Recovery

```bash
splendor source forget <source-id|logical-id|title|path>
splendor source forget --matching ".mypy_cache/**"
splendor source reconcile <source-id|logical-id|title|path>
splendor queue clean --orphaned
splendor queue clean --superseded
splendor queue clean --completed
```

Recovery commands preview by default and require `--apply` before deleting or rewriting source
registry state.

## Ingest And Queue Work

```bash
splendor ingest <source-id|title|path|logical-id>
splendor ingest --pending
splendor ingest --pending --apply
splendor ingest --changed
splendor queue inspect
splendor queue retry <job-id>
splendor repair ingest <source-id>
```

`ingest --pending` previews pending queue work. Use `ingest --pending --apply` to drain the queue.
`ingest --changed` is the focused repair path for checksum-drifted curated workspace sources whose
previous queue records are already done.

## Query And Answers

```bash
splendor query "current roadmap"
splendor query "current roadmap" --json
splendor query "current roadmap" --tag planning
splendor query "current roadmap" --source README.md
splendor query "current roadmap" --no-save
splendor file-answer --from-last-query --title "Roadmap answer"
```

`query` searches local Splendor records and saves the last query by default. `file-answer` can turn
that last query into a maintained planning/wiki answer file for review.

## Agent Handoff

```bash
splendor brief
splendor brief --agent-context "continue the next roadmap slice"
splendor brief --agent-context --since main "review this branch"
splendor brief --agent-context --no-git "summarize current planning"
splendor suggest-next "continue the next roadmap slice"
splendor suggest-next --json "continue the next roadmap slice"
splendor pr-summary --since main
```

Agent handoff commands are read-only. They combine query matches, current authority, planning
records, git/PR context when available, and maintenance state. For normal implementation goals,
work context should lead and Splendor maintenance should remain separate.

## Planning Records

```bash
splendor task create "Publish MVP docs" --priority high
splendor task list
splendor milestone create "Milestone name"
splendor decision create "Decision title"
splendor question create "Question title"
```

Planning records live under `planning/` as reviewable markdown files.

## Wiki Maintenance

```bash
splendor add-topic "Topic title"
splendor wiki status
splendor wiki suggest <source-id>
splendor wiki compile <source-id>
splendor wiki compile <source-id> --page wiki/topic.md
splendor wiki compile <source-id> --page wiki/topic.md --apply --proposal-hash <hash>
splendor wiki rebuild-index
```

Generated source summaries and maintained wiki pages are separate. `wiki compile` can preview a
single maintained-page update and requires an explicit proposal hash to apply it.

## Workspace Refresh

```bash
splendor workspace refresh --changed
splendor workspace refresh --changed --ingest
splendor workspace refresh --changed --ingest --rebuild-index
splendor workspace refresh --changed --ingest --prune-superseded --update-topic-refs --rebuild-index --apply
```

Workspace refresh composes source freshness, source refresh, targeted ingest, index rebuilds,
superseded-summary pruning, and maintained source-ref migration. It previews by default.

## Local State Review

Common generated paths:

- `wiki/`: generated source summaries plus maintained wiki pages
- `planning/`: task, milestone, decision, and question records
- `state/`: source manifests plus queue/run/query records
- `reports/`: explicit lint, health, freshness, and discovery reports
- `derived/`: parsed, OCR, or other derived artifacts

Generated state is meant to be inspected before commit. `splendor pr-summary --since <base>` helps
separate meaningful wiki/source changes from mechanical queue/run/report churn.
