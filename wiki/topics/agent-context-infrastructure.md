---
schema_version: '1'
kind: topic
title: Agent Context Infrastructure
page_id: topic-agent-context-infrastructure
status: active
review_state: machine-generated
source_refs:
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
generated_by_run_ids: []
last_generated_at: '2026-04-30T09:22:14+00:00'
last_reviewed_at: null
confidence: 0.74
related_pages:
- topic-llm-assisted-knowledge-work
- topic-llm-wiki-tool-landscape
- architecture-splendor-as-llm-wiki-compiler
tags:
- agents
- context-engineering
- repository-memory
provenance_links:
- source_id: src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
  page_id: null
  run_id: run-src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4-20260430T092129520858Z
  path_ref: raw/imports/dogfood-knowledge-work/round-2-context-engineering-and-repo-memory.md
  role: generated-from
  note: Round 2 context-engineering dogfood note.
contradictions: []
---

# Agent Context Infrastructure

Splendor can be read as repository-local context infrastructure: it gives humans and agents a
durable place to store what matters between sessions without stuffing every fact into an instruction
file or relying on chat history.

## Working Model

The repository context stack is:

- `AGENTS.md` as the compact operating map,
- `docs/` for long-form product and architecture truth,
- `wiki/` for compiled source-backed knowledge,
- `planning/` for tasks, questions, decisions, and milestones,
- `state/` for manifests, queue records, runs, query snapshots, and maintenance reports.

This matches the broader context-engineering lesson that context is scarce and should be assembled
deliberately. The durable repository artifacts carry long-term memory; each model invocation should
receive only the slice needed for the current task.

## Product Implication

Search is necessary but not sufficient. A user doing real work needs an orientation product:

- what is known,
- what changed recently,
- what sources support the current understanding,
- what tasks or questions remain open,
- what generated pages are stale, contested, or machine-generated.

That suggests a future project-briefing command or UI view that assembles wiki, planning, source,
and run state into a compact working brief.

## Dogfood Finding

During three knowledge-work rounds, `splendor query --no-save` was useful as a non-mutating
inspection command. The friction was the next step: deciding what to file, what synthesis pages to
edit, and which product issues should become roadmap work. Splendor should reduce that handoff with
explicit wiki status, source-impact suggestions, and briefing support.
