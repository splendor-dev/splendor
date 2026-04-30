---
schema_version: '1'
kind: task
task_id: task-capture-real-ingest-run-durations
title: Capture real ingest run durations
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T12:55:11+00:00'
updated_at: '2026-04-30T12:55:11+00:00'
depends_on: []
source_refs:
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
page_refs:
- docs/dogfood_knowledge_work_report.md
run_refs:
- state/runs/run-src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6-20260430T092101207478Z.json
- state/runs/run-src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4-20260430T092129520858Z.json
- state/runs/run-src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b-20260430T092201788872Z.json
---

## Context

The M9-P1.3 dogfood ingest records all have identical `started_at` and `finished_at` timestamps,
which makes them zero-duration runs. This appears to be a runtime recording issue rather than a
problem with the dogfood documentation itself.

GitHub issue: https://github.com/splendor-dev/splendor/issues/47.

## Follow-up

Capture the ingest run start timestamp before work begins and write a distinct finish timestamp at
completion. Add regression coverage where feasible. Do not hand-edit historical run records unless a
reliable source for corrected timestamps exists.
