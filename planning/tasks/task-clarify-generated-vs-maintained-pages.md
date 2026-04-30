---
schema_version: '1'
kind: task
task_id: task-clarify-generated-vs-maintained-pages
title: Clarify generated versus maintained wiki pages
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T12:35:48+00:00'
updated_at: '2026-04-30T12:35:48+00:00'
depends_on:
- task-add-wiki-status-suggest-compile-loop
source_refs:
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
page_refs:
- docs/dogfood_knowledge_work_report.md
- docs/splendor_product_spec.md
run_refs: []
---

## Context

Dogfood use made the page-state distinction visible: a source-summary page, a draft synthesis page,
a reviewed synthesis page, and a stale page require different user expectations. Today that
distinction exists partly through frontmatter and provenance, but the command output, docs, and web
UI do not yet make it obvious.

Roadmap slice: `M10-P0.3`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/45.

## Follow-up

Clarify generated versus maintained pages across docs, lint/status output, query results, and the
web UI. Users should be able to tell whether a page is a generated artifact, unreviewed synthesis,
reviewed synthesis, contested synthesis, or stale synthesis without inspecting raw frontmatter.
