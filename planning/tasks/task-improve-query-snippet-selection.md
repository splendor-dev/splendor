---
schema_version: '1'
kind: task
task_id: task-improve-query-snippet-selection
title: Improve query snippet selection for generated source summaries
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T09:22:14+00:00'
updated_at: '2026-04-30T09:22:14+00:00'
depends_on: []
source_refs:
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
page_refs:
- wiki/sources/src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4.md
- wiki/sources/src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b.md
run_refs: []
---

## Context

Dogfood queries often ranked the correct page but sometimes showed snippets from generated
`Key Facts` or provenance boilerplate instead of the source note's substantive claims.

Roadmap slice: `M10-P0.3`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/44.

## Follow-up

Prefer sections such as `Core Claims`, `Design Implications`, `Product Experience Notes`, and
content extracts over deterministic metadata when rendering snippets for source-summary pages.
