# Karpathy LLM Wiki Pattern

Source URL: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

Related announcement URL: https://x.com/karpathy/status/2039805659525644595

## Source Note

Andrej Karpathy's LLM Wiki note describes a pattern for using LLM agents to maintain a persistent
personal knowledge base. The central contrast is with ordinary RAG-style document interaction:
retrieval at answer time can find fragments, but it does not accumulate synthesis across sessions.

The proposed alternative is a maintained wiki layer between raw sources and user questions. New
sources are not only indexed; they are read, summarized, linked into existing pages, and used to
revise prior synthesis when they strengthen, challenge, or contradict it.

## Core Claims

- The wiki is a persistent, compounding artifact rather than a transient answer.
- Raw sources stay immutable and remain the source of truth.
- The generated wiki consists of markdown pages such as summaries, entities, concepts,
  comparisons, overview pages, and synthesis pages.
- The LLM is responsible for repetitive maintenance work: summarization, cross-references,
  consistency, contradiction surfacing, filing answers, and updating index/log files.
- The human remains responsible for source selection, supervision, questions, and judgment.
- `index.md` and `log.md` are special navigation files: one content-oriented and one chronological.
- Query outputs can be filed back into the wiki so research work compounds instead of disappearing
  into chat history.
- Periodic linting should look for contradictions, stale claims, orphan pages, missing
  cross-references, and gaps that need new sources.

## Design Implications for Splendor

Splendor already mirrors this architecture with `raw/`, `wiki/`, `planning/`, `state/`, lint,
health, query snapshots, provenance, and a CLI-first workflow. The strongest alignment is that
Splendor treats the filesystem as durable state and aims to make source-to-page provenance explicit.

The next useful step for Splendor is to make the local wiki browsable enough that humans and agents
can inspect accumulated synthesis without going straight back to raw source manifests.
