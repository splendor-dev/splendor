---
schema_version: '1'
kind: topic
title: LLM Wiki Tool Landscape
page_id: topic-llm-wiki-tool-landscape
status: active
review_state: machine-generated
source_refs:
- src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
- src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
generated_by_run_ids:
- run-src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6-20260430T092101207478Z
- run-src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b-20260430T092201788872Z
last_generated_at: '2026-04-30T09:22:14+00:00'
last_reviewed_at: null
confidence: 0.73
related_pages:
- concept-llm-wiki-pattern
- topic-agent-context-infrastructure
- architecture-splendor-as-llm-wiki-compiler
tags:
- llm-wiki
- competitive-research
- product-strategy
provenance_links:
- source_id: src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6
  page_id: null
  run_id: run-src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6-20260430T092101207478Z
  path_ref: raw/imports/dogfood-knowledge-work/round-1-llm-wiki-implementation-landscape.md
  role: generated-from
  note: Round 1 implementation-landscape dogfood note.
- source_id: src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b
  page_id: null
  run_id: run-src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b-20260430T092201788872Z
  path_ref: raw/imports/dogfood-knowledge-work/round-3-competitive-feature-map.md
  role: generated-from
  note: Round 3 competitive feature-map dogfood note.
contradictions: []
---

# LLM Wiki Tool Landscape

LLM Wiki tools are converging on a common workflow: keep source material stable, compile durable
wiki pages, expose agent-facing operations, and validate the resulting knowledge base.

## Common Product Loop

The recurring loop across current tools is:

1. ingest sources into a workspace,
2. compile or update wiki pages,
3. query the compiled knowledge,
4. save useful answers back into the wiki,
5. lint the wiki for quality, links, stale pages, and contradictions,
6. expose the loop through a CLI, web UI, MCP server, or all three.

Splendor currently implements the safe filesystem parts of this loop well, especially source
manifests, run records, query output, lint, health, and planning objects. Its biggest gap is that
the compile/update step is not yet a named product operation.

## Feature Axes

Important product axes in the surrounding landscape:

- explicit compile pipelines versus source-summary-only ingestion,
- MCP tools and resources for agent-native use,
- typed page schemas and review queues,
- claim-level or paragraph-level provenance,
- semantic search and reranking for larger corpora,
- rich document parsing for PDFs, office files, tables, formulas, and scanned pages,
- exports such as `llms.txt`, JSON, graph formats, or slide decks.

Splendor should add these only where they support its core identity: a git-native, reviewable,
schema-driven knowledge compiler for code-and-research repositories.

## Product Strategy

The near-term priority is not to out-feature richer apps. Splendor should first make the text-native
knowledge loop complete:

- source registration should naturally lead to ingestion,
- ingestion should produce useful source summaries,
- a compile/suggest step should identify affected synthesis pages,
- query and file-answer should make good outputs persistent,
- lint and health should keep the workspace trustworthy.

Rich-source handling remains important, but it should build on a stronger compile loop rather than
arrive as a separate ingestion surface.
