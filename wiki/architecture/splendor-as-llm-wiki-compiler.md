---
schema_version: '1'
kind: architecture
title: Splendor as an LLM Wiki Compiler
page_id: architecture-splendor-as-llm-wiki-compiler
status: active
review_state: machine-generated
source_refs:
- src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
- src-9143c8df18710ac189ed8d1fa38a8df92509acadedaaf96ab40e189ab4877a41
- src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
generated_by_run_ids: []
last_generated_at: '2026-04-30T05:18:00+00:00'
last_reviewed_at: null
confidence: 0.74
related_pages:
- concept-llm-wiki-pattern
- topic-llm-assisted-knowledge-work
- topic-llm-wiki-tool-landscape
tags:
- architecture
- splendor
- llm-wiki
provenance_links:
- source_id: src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
  page_id: null
  run_id: null
  path_ref: raw/imports/llm-knowledge-work/karpathy-llm-wiki-pattern.md
  role: generated-from
  note: Pattern source note.
- source_id: src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
  page_id: null
  run_id: null
  path_ref: raw/imports/llm-knowledge-work/lucas-astorian-llmwiki-implementation.md
  role: generated-from
  note: Implementation comparison source note.
contradictions: []
---

# Splendor as an LLM Wiki Compiler

Splendor can be understood as a schema-driven compiler from source material into durable project
knowledge.

## Architectural Mapping

Karpathy's LLM Wiki pattern maps onto Splendor this way:

- raw sources map to `raw/` plus source manifests under `state/manifests/sources/`,
- generated wiki pages map to `wiki/`,
- operating instructions map to `AGENTS.md`, `.agent-plan.md`, and roadmap docs,
- query and filed answers map to `splendor query` and `splendor file-answer`,
- lint and review map to `splendor lint`, `splendor health`, review states, and planning tasks.

The web UI is deliberately secondary. Its job is to make the compiled artifact browsable, not to
replace the CLI as the operational contract.

## Contrast With LLM Wiki Implementations

The open-source LLM Wiki implementation uses a richer local app and derived SQLite indexing.
Splendor takes a more conservative path: tracked JSON and markdown state, deterministic commands,
and explicit schemas before richer indexing.

That tradeoff favors reviewability and git-native automation over immediate UI completeness.

## Compile Loop Gap

The dogfood extension surfaced a sharper architectural distinction: Splendor has source
registration, source-summary ingestion, query, file-answer, lint, and health, but it does not yet
have a named compile/update step for related concept, topic, comparison, and architecture pages.

That gap is product-visible. After a source is ingested, the user can verify that it exists and is
searchable, but must manually decide which synthesis pages should change. A future compile step
should preserve Splendor's reviewable file contracts while making source-to-synthesis maintenance a
first-class workflow.

## Dogfood Finding

Seeding these sources revealed a concrete product issue: contradiction review can produce
false-positive review tasks when deterministic source-summary boilerplate differs only by source
path. That is useful knowledge for future Milestone 10 or contradiction-review hardening work.

The later dogfood rounds added two more findings: `ingest --pending` did not pick up newly
registered sources in this workflow, and query snippets can select generated key-fact boilerplate
instead of substantive source claims. Both issues affect trust in the knowledge loop more than the
raw storage model.
