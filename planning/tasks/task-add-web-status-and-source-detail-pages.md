---
schema_version: '1'
kind: task
task_id: task-add-web-status-and-source-detail-pages
title: Add web status overview and source detail pages
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
- docs/splendor_mvp_to_v1_roadmap.md
run_refs: []
---

## Context

The read-only web UI is useful for browsing, but the dogfood pass still required terminal context to
understand source counts, recent ingest activity, pending jobs, review state, and whether source
summaries have been carried into synthesis pages.

Roadmap slice: `M10-P0.3`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/45.

## Follow-up

Add a read-only status overview page and source detail pages after the CLI status/suggest contract
exists. The overview should surface source counts, recent runs, pending jobs, wiki page counts,
stale/generated/review-needed pages, and latest log entries. Source detail should show the source
manifest, generated summary page, ingest run, provenance, and affected synthesis-page suggestions.
