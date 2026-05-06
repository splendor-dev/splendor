---
schema_version: '1'
kind: task
task_id: task-add-dogfood-workflow-polish
title: Add dogfood workflow polish and next-action hints
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T12:35:48+00:00'
updated_at: '2026-04-30T12:35:48+00:00'
depends_on:
- task-fix-add-source-pending-ingest-handoff
- task-add-wiki-status-suggest-compile-loop
source_refs:
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
page_refs:
- docs/evaluations/dogfood_knowledge_work_report.md
- docs/guides/dogfooding.md
run_refs: []
---

## Context

As a user, the core loop still requires too much memory: register a source, find or copy a long
source ID, ingest it, inspect the generated page, decide which synthesis pages should change, and
then manually keep the wiki coherent. Each command works better when it tells the user the next
exact action.

Roadmap slice: `M10-P0.3`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/42.

## Follow-up

Add restrained next-action hints after major commands. Good examples include printing the exact
`splendor ingest <source-id>` command after `add-source`, pointing to
`splendor wiki suggest <source-id>` after ingest once that command exists, and making
query/file-answer output clear about whether there is a follow-up filing or review step.
