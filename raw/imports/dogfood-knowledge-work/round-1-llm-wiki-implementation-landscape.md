# Round 1: LLM Wiki Implementation Landscape

Source URLs:

- https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- https://github.com/lucasastorian/llmwiki
- https://denser.ai/blog/llm-wiki-karpathy-knowledge-base/

## Source Note

This note expands Splendor's existing LLM Wiki seed material after a first dogfood pass through the
current repository wiki. The strongest existing wiki pages already captured the raw/written-wiki
split, but they under-described the emerging product landscape around the pattern and how quickly
implementations are converging on agent-facing tools.

## Core Claims

- The LLM Wiki pattern is no longer only an idea-file pattern. It has become a fast-moving product
  category with local apps, MCP servers, wiki compilers, hosted variants, and commercial RAG vendors
  reframing their roadmaps around compiled knowledge.
- The common shape is stable: source files remain durable, a maintained markdown wiki becomes the
  working knowledge layer, and agent instructions or schemas define the maintenance contract.
- Implementations differ most strongly on where they place complexity: hidden local indexes,
  semantic search, richer web UI, MCP surfaces, typed schemas, review queues, and multimodal
  extraction.
- Splendor's distinctive position is its conservative file-contract bias: git-visible manifests,
  queue records, run records, lint reports, planning objects, and deterministic commands before
  hidden indexing or rich UI.
- The market signal is not that Splendor should copy a fuller app immediately. The signal is that
  humans and agents expect a full loop: ingest, compile/update pages, query, file answers, lint, and
  inspect operational state.

## Design Implications

Splendor should keep the raw-source, wiki, and instruction-file triangle as a first-class concept,
but the word "ingest" currently hides two different jobs:

1. Register and summarize a source.
2. Compile that source into existing concept, topic, comparison, and architecture pages.

Current Splendor ingest performs the first job deterministically. Dogfooding shows that the second
job remains too manual for sustained knowledge work. The roadmap should add an explicit compile or
update step rather than overloading deterministic source-summary generation.

## Product Experience Notes

Reading the current wiki before adding this source was genuinely useful: I could learn the product
premise, see prior source summaries, and query for dogfood findings without reading the entire repo.
The weak point was follow-through. After finding a new source, I had to decide manually where
analysis should live, how to update synthesis pages, and how to keep index/log/provenance coherent.

The CLI makes source registration and ingestion feel safe. The missing user affordance is an
opinionated "continue the knowledge loop" command that says what pages should change next.
