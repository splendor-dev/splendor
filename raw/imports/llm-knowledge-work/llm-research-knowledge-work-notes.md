# LLM Research and Knowledge Work Notes

Source URLs:

- https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- https://github.com/lucasastorian/llmwiki
- https://x.com/karpathy/status/2039805659525644595

## Source Note

This note distills design implications for Splendor from the LLM Wiki pattern and its first
open-source implementation. It is intentionally a local synthesis note, not a verbatim mirror of any
external source.

## LLM Knowledge Work Loop

LLM-assisted research becomes more useful when the agent is allowed to leave durable artifacts:

1. Select or register a source.
2. Extract key claims and relevant context.
3. Integrate those claims into existing pages.
4. Record provenance back to the source and run.
5. Surface contradictions or stale assumptions.
6. File useful answers back into the wiki.
7. Periodically lint the knowledge base for health.

This loop differs from ordinary chat because the user and agent are improving the workspace itself,
not only producing a one-time answer.

## Splendor Relevance

Splendor can treat research as versioned knowledge compilation. The CLI, schemas, manifests, query
snapshots, lint reports, and now the local web UI are all supporting machinery around that loop.

The most important product test is whether a new agent can enter the repository, browse the current
wiki, understand what has already been learned, and continue the work without relying on chat
history.
