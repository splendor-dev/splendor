---
schema_version: '1'
kind: topic
title: LLM-Assisted Knowledge Work
page_id: topic-llm-assisted-knowledge-work
status: active
review_state: machine-generated
source_refs:
- src-51e62cdae9baf8dfd550ac791f21a7cc11cca2e372865907d35ab6eaeea31dac
- src-9143c8df18710ac189ed8d1fa38a8df92509acadedaaf96ab40e189ab4877a41
- src-e7f25dbe0c913cb8938d30e2da9d2e4d03afbab29f519db40ea90b23e0113bfd
- src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4
generated_by_run_ids: []
last_generated_at: '2026-04-30T09:22:14+00:00'
last_reviewed_at: null
confidence: 0.76
related_pages:
- concept-llm-wiki-pattern
- architecture-splendor-as-llm-wiki-compiler
- topic-agent-context-infrastructure
tags:
- research
- knowledge-work
- agents
provenance_links:
- source_id: src-9143c8df18710ac189ed8d1fa38a8df92509acadedaaf96ab40e189ab4877a41
  page_id: null
  run_id: null
  path_ref: raw/imports/llm-knowledge-work/llm-research-knowledge-work-notes.md
  role: generated-from
  note: Local synthesis source note.
contradictions: []
---

# LLM-Assisted Knowledge Work

LLM-assisted knowledge work is most valuable when the agent changes the state of the workspace, not
only the state of the conversation.

## Working Loop

A practical loop is:

1. Register a source.
2. Extract claims, vocabulary, and links.
3. Update source summaries and related concept/topic pages.
4. Preserve provenance back to source files and runs.
5. File useful answers into the wiki.
6. Run lint and health checks to find broken references, stale claims, and missing review work.

The loop gives each session a durable residue. A future agent can search and browse the wiki before
touching raw material again.

## Human And Agent Responsibilities

The human chooses sources, sets priorities, and reviews synthesis. The LLM handles repetitive
bookkeeping: filing, summarizing, linking, comparing, and keeping the wiki coherent.

This division is important. Without human curation, the wiki can fill with low-value generated
pages. Without agent maintenance, a hand-maintained wiki tends to decay as source volume grows.

## Product Test For Splendor

The Splendor dogfood test is simple: can a new agent open the repository, inspect the wiki, and
learn the project context without relying on prior chat history?

After the LLM Wiki source seeding, the answer is closer to yes. The browse/search UI now has source
summaries, concept pages, and planning tasks to inspect, but the false-positive contradiction tasks
also show that review automation needs tighter semantics.

## Repository Memory

The second dogfood round connected Splendor to context-engineering practice. A maintained wiki,
planning records, and run/source state act as durable memory outside the model context window. That
matters because real research and software work exceeds a single conversation: the system needs
compact entry points, source-backed synthesis, and explicit planning state so later agents can
resume without replaying raw history.

The missing product layer is a briefing surface that assembles the relevant wiki pages, active
planning records, recent runs, stale generated pages, and contested areas for a specific goal.
