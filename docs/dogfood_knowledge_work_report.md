# Dogfood Knowledge Work Report

Date: 2026-04-30

## Section A: Knowledge Work and Wiki Extension

This dogfood pass used Splendor on the Splendor repository as a real knowledge workspace. The loop
was repeated three times: inspect the current wiki, search for external sources, write a local
source note, register and ingest it, query the wiki, and then synthesize durable wiki updates.

### Round 1: LLM Wiki implementation landscape

Added `raw/imports/dogfood-knowledge-work/round-1-llm-wiki-implementation-landscape.md` and
ingested it as `src-6be68f3b5ee70bf209d78171363cbd857c72f331dbdd13ddc79fd2f7d8c188a6`.

The source note extended the existing LLM Wiki pages with current implementation-landscape context:
local apps, MCP servers, hosted variants, wiki compilers, and commercial RAG vendors are converging
on a full loop of ingest, compile/update, query, file, and lint.

### Round 2: Context engineering and repository memory

Added `raw/imports/dogfood-knowledge-work/round-2-context-engineering-and-repo-memory.md` and
ingested it as `src-a1af8da17b1e5f3c5616150339ba58f1832bc91fccf9a534c59063d3ca0173d4`.

The source note connected Splendor to broader agent context-engineering practice. The main finding
is that Splendor is naturally positioned as repository-local context infrastructure: `AGENTS.md` is
the map, while `docs/`, `wiki/`, `planning/`, and `state/` hold durable working memory.

### Round 3: Competitive feature map

Added `raw/imports/dogfood-knowledge-work/round-3-competitive-feature-map.md` and ingested it as
`src-c2176196c8d0e5edd5f231021c55821d970230fada194b4a3d53b24abd77921b`.

The source note compared Splendor with adjacent tools that emphasize explicit compile pipelines,
MCP resources, rich document reading, hybrid retrieval, typed page kinds, review queues, and
claim-level provenance. The conclusion is that Splendor should complete its text-native knowledge
loop before expanding aggressively into rich document parsing.

### Wiki updates made

- Added `wiki/topics/llm-wiki-tool-landscape.md`.
- Added `wiki/topics/agent-context-infrastructure.md`.
- Updated `wiki/topics/llm-assisted-knowledge-work.md` with repository-memory implications.
- Updated `wiki/architecture/splendor-as-llm-wiki-compiler.md` with the compile-loop gap and
  dogfood findings.
- Updated `wiki/index.md` and `wiki/log.md` so the new sources and synthesis pages are discoverable.

## Section B: Product Experience, Bugs, and Roadmap Thoughts

### What worked

- Existing wiki pages were sufficient to orient a new agent without prior chat history.
- `splendor query --no-save` was useful for exploratory, non-mutating inspection.
- Explicit source manifests, run records, source-summary pages, and provenance-rich query output
  made the workflow feel inspectable and safe.
- Writing curated markdown notes before ingestion materially improved source-summary usefulness.

### Bugs or kinks

- `splendor ingest --pending` did not process newly registered sources during this workflow. It
  repeatedly skipped older done items, while the newly registered source required explicit
  `splendor ingest <source-id>`.
- Source IDs are cumbersome in a manual loop. After `add-source`, the next command naturally wants
  to ingest that exact source, but the user must copy a long ID correctly.
- Query snippets can rank the right page but show generated key-fact/provenance boilerplate instead
  of substantive source claims.
- The current ingest command creates source summaries, but it does not suggest or update related
  concept/topic/architecture pages. That leaves the most important knowledge-maintenance decision
  outside the tool.

### Do now

- Fix or clarify the `add-source` to `ingest --pending` handoff.
- Add a low-friction next step after registration, such as `add-source --ingest`, outputting a
  ready-to-run ingest command, or making the queue behavior match user expectations.
- Improve query snippet selection to prefer source content sections such as `Core Claims`, `Design
  Implications`, and `Product Experience Notes` over deterministic metadata blocks.

### Put on the roadmap

- Add a `splendor wiki status` command or UI view showing page counts, source counts, pending
  sources, recent runs, stale pages, machine-generated pages, and review work.
- Add `splendor wiki suggest <source-id>` to identify synthesis pages likely affected by a source.
- Add an explicit compile/update workflow for concept, topic, architecture, comparison, and
  overview pages, probably review-gated at first.
- Add a project briefing command or UI view that assembles source-backed wiki knowledge, active
  planning records, recent run state, and known gaps for a user goal.
- Keep rich-source handling behind the stronger text-native loop; PDF/OCR/document parsing should
  enter through the same source-resolution and provenance contracts.

### Design and roadmap updates recommended

- Treat source-summary pages as ingestion artifacts and concept/topic/architecture/comparison pages
  as the maintained synthesis layer.
- Add `M10-P0` before deeper planning/runs UI and rich-source work, focused on wiki status,
  source-impact suggestions, and project briefing.
- Add `splendor wiki status` and `splendor wiki suggest <source-id>` before a mutating compile
  command.
- Define a future review-gated `splendor wiki compile <source-id>` workflow for maintaining
  synthesis pages.
- Add a project briefing command or UI view that assembles repository-local context for a stated
  goal.

### Product workflow updates recommended

- Add `M10-P0.3` as a dogfood workflow-polish slice after status/suggest and project briefing.
- Fix the `add-source -> ingest --pending` handoff as a high-priority workflow bug.
- Improve query snippets so source-summary results prefer claim-bearing source text over generated
  metadata.
- Add restrained next-action hints after `add-source`, `ingest`, `query`, and `file-answer`.
- Add read-only web status overview and source detail pages after the CLI status contract exists.
- Clarify generated artifacts, draft synthesis, reviewed synthesis, contested pages, and stale pages
  across docs, lint/status output, query results, and web UI.

Follow-up issues opened:

- https://github.com/splendor-dev/splendor/issues/40 — `M10-P0.1` wiki status and source-impact
  suggestions.
- https://github.com/splendor-dev/splendor/issues/41 — `M10-P0.2` project briefing and
  compile-loop contract.
- https://github.com/splendor-dev/splendor/issues/42 — `M10-P0.3` dogfood workflow polish and
  next-action hints.
- https://github.com/splendor-dev/splendor/issues/43 — add-source to pending-ingest handoff.
- https://github.com/splendor-dev/splendor/issues/44 — query snippets for generated source
  summaries.
- https://github.com/splendor-dev/splendor/issues/45 — web status overview and source detail
  pages.
- https://github.com/splendor-dev/splendor/issues/46 — generated versus maintained page-state
  visibility.
- https://github.com/splendor-dev/splendor/issues/47 — real ingest run durations in run records.
