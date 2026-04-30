---
schema_version: '1'
kind: task
task_id: task-harden-contradiction-review-boilerplate
title: Harden contradiction review against source-summary boilerplate false positives
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-04-30T05:22:00+00:00'
updated_at: '2026-04-30T05:22:00+00:00'
depends_on: []
source_refs:
- src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
- src-3e2ae8bad71969d960fabb9ea0670dfb6db9f6c62d0484a445cf3ff5e2af6f1a
- src-9143c8df18710ac189ed8d1fa38a8df92509acadedaaf96ab40e189ab4877a41
- src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
page_refs:
- wiki/sources/src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac.md
- wiki/sources/src-3e2ae8bad71969d960fabb9ea0670dfb6db9f6c62d0484a445cf3ff5e2af6f1a.md
- wiki/sources/src-9143c8df18710ac189ed8d1fa38a8df92509acadedaaf96ab40e189ab4877a41.md
- wiki/sources/src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd.md
run_refs: []
---

## Context

Dogfooding Splendor's ingest path on several related LLM Wiki source notes created false-positive
contradiction review tasks. The compared source-summary pages used similar deterministic boilerplate
whose only meaningful difference was the source path.

## Follow-up

Future contradiction review should ignore or down-rank boilerplate source-summary prose and compare
claims extracted from source content instead of generic ingestion scaffolding.
