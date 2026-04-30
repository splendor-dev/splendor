---
schema_version: '1'
kind: task
task_id: task-fix-add-source-pending-ingest-handoff
title: Fix add-source to pending-ingest handoff
status: todo
priority: high
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T09:22:14+00:00'
updated_at: '2026-04-30T09:22:14+00:00'
depends_on: []
source_refs:
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
page_refs:
- wiki/topics/agent-context-infrastructure.md
- wiki/topics/llm-wiki-tool-landscape.md
run_refs: []
---

## Context

During three dogfood rounds, `splendor add-source` registered each new source successfully, but
`splendor ingest --pending` repeatedly skipped older done queue records and did not process the
newly registered source. Each new source required explicit `splendor ingest <source-id>`.

Roadmap slice: `M10-P0.1`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/43.

## Follow-up

Clarify and fix the handoff between registration and pending ingestion. Good outcomes include a
working pending queue entry, an `add-source --ingest` shortcut, or command output that gives the
next exact ingest command without requiring users to manage long source IDs manually.
