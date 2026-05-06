---
schema_version: '1'
kind: task
task_id: task-add-project-briefing-and-compile-contract
title: Add project briefing and compile-loop contract
status: todo
priority: high
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
- docs/evaluations/dogfood_knowledge_work_report.md
- docs/splendor_product_spec.md
- docs/splendor_mvp_to_v1_roadmap.md
run_refs: []
---

## Context

The knowledge-work dogfood pass showed that agents and humans need a compact orientation step
before continuing work in a repository-local wiki. Search can find relevant records, but it does not
assemble the working context, current planning state, recent runs, unresolved questions, and known
stale or machine-generated pages into one brief.

Roadmap slice: `M10-P0.2`.

GitHub issue: https://github.com/splendor-dev/splendor/issues/41.

The same pass also showed that source-summary generation is distinct from synthesis-page
maintenance. The compile/update workflow should be explicit and review-gated before it mutates
concept, topic, architecture, comparison, or overview pages.

## Follow-up

Add a project briefing command or web view that accepts a goal and assembles wiki, planning, source,
and recent run context. Define the reviewed compile/update contract for `splendor wiki compile <source-id>`
or an equivalent operation, including provenance, proposed diffs, and explicit accept semantics
before synthesis pages are updated.
