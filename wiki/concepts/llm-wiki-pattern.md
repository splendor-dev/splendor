---
schema_version: '1'
kind: concept
title: LLM Wiki Pattern
page_id: concept-llm-wiki-pattern
status: active
review_state: machine-generated
source_refs:
- src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
- src-3e2ae8bad71969d960fabb9ea0670dfb6db9f6c62d0484a445cf3ff5e2af6f1a
- src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
generated_by_run_ids: []
last_generated_at: '2026-04-30T05:18:00+00:00'
last_reviewed_at: null
confidence: 0.78
related_pages:
- topic-llm-assisted-knowledge-work
- topic-llm-wiki-tool-landscape
- architecture-splendor-as-llm-wiki-compiler
tags:
- llm-wiki
- knowledge-work
- research
provenance_links:
- source_id: src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
  page_id: null
  run_id: null
  path_ref: raw/imports/llm-knowledge-work/karpathy-llm-wiki-pattern.md
  role: generated-from
  note: Karpathy idea-file source note.
- source_id: src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
  page_id: null
  run_id: null
  path_ref: raw/imports/llm-knowledge-work/lucas-astorian-llmwiki-implementation.md
  role: generated-from
  note: Open-source implementation source note.
contradictions: []
---

# LLM Wiki Pattern

The LLM Wiki pattern treats an LLM as a maintainer of a persistent markdown knowledge base rather
than as a one-shot answer generator over uploaded files.

## Core Model

The pattern has three durable layers:

- raw sources that remain stable and auditable,
- a generated wiki that accumulates summaries, concepts, entities, comparisons, and answers,
- operating instructions that teach the agent how to ingest, query, lint, and maintain the wiki.

The key product idea is compounding synthesis. A useful answer, source summary, contradiction note,
or comparison should become workspace state instead of disappearing into chat history.

## Why It Matters

Plain retrieval can answer a question by finding fragments at query time, but it usually does not
improve the knowledge base. The LLM Wiki pattern asks the agent to pay the maintenance cost once:
summarize the source, update related pages, add cross-links, preserve provenance, and flag
conflicts.

That shifts LLM research from repeated rediscovery toward knowledge compilation.

## Splendor Fit

Splendor is an implementation of this pattern with a stronger schema and deterministic CLI bias:

- source manifests track registered inputs,
- wiki pages are markdown artifacts with frontmatter,
- runs and queues record machine work,
- lint and health commands validate state,
- the web UI makes accumulated knowledge inspectable.

The missing long-term piece is not the premise; it is making the maintenance loop ergonomic enough
that humans and agents will actually use it every day.
