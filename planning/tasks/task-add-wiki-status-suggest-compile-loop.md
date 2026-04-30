---
schema_version: '1'
kind: task
task_id: task-add-wiki-status-suggest-compile-loop
title: Add wiki status, source-impact suggestions, and compile loop
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
- wiki/topics/llm-wiki-tool-landscape.md
- wiki/architecture/splendor-as-llm-wiki-compiler.md
run_refs: []
---

## Context

After each source was ingested, Splendor made the source summary searchable but did not suggest
which concept, topic, or architecture pages should be updated. The user had to hold the knowledge
maintenance loop manually.

## Follow-up

Design a text-native wiki-maintenance loop before richer source handling expands:

- `splendor wiki status` for source/page/run/review state,
- `splendor wiki suggest <source-id>` for affected synthesis pages,
- `splendor wiki compile <source-id>` or equivalent for reviewable page updates.
