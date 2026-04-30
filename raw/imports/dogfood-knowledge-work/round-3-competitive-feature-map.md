# Round 3: Competitive Feature Map for LLM Wiki Tools

Source URLs:

- https://github.com/atomicmemory/llm-wiki-compiler
- https://github.com/OpenDataLab/MinerU-Document-Explorer
- https://github.com/opendatalab/MinerU

## Source Note

This round compares Splendor with adjacent open-source tools that are making the LLM Wiki pattern
more operational. The relevant contrast is not "which tool has more features"; it is which product
loop each tool optimizes.

## Core Claims

- `atomicmemory/llm-wiki-compiler` emphasizes an explicit compile pipeline, MCP resources and
  tools, saved query answers, linting, typed page kinds, review candidates, claim-level provenance,
  exports, and semantic query routing. That makes the compiler step a named product operation.
- MinerU Document Explorer emphasizes document navigation and rich source handling: retrieve,
  deep-read, and ingest tool suites; PDF/DOCX/PPTX/Markdown support; BM25 plus vector plus rerank
  retrieval; and MCP integration for agents.
- MinerU itself shows how much product surface lives below "ingest" once rich documents enter the
  system: layout reconstruction, reading order, tables, formulas, scanned documents, handwriting,
  OCR, VLM parsing, and structured markdown or JSON outputs.
- Splendor should not rush into the full rich-document stack before its text-native compile loop is
  strong. The competitive risk is less "we do not parse PDFs yet" and more "after ingesting a useful
  source, the user still has to manually update the durable synthesis layer."
- The feature map points toward three near-term priorities: explicit compile/update suggestions,
  operational visibility for queues/runs, and a project briefing command that assembles context for
  agents.

## Design Implications

Splendor's roadmap has the right high-level ordering: web browse/search, planning/runs visibility,
queue repair, then rich source handling. Dogfooding suggests one additional connective slice before
or alongside planning/runs UI: a knowledge-loop command that proposes or performs deterministic
wiki-maintenance next steps after source ingestion.

Possible shape:

- `splendor wiki status`: page counts, source counts, stale pages, orphan pages, pending sources,
  last runs, and pages needing review.
- `splendor wiki suggest <source-id>`: list concept/topic/architecture pages likely affected by a
  source.
- `splendor wiki compile <source-id>`: update synthesis pages with an auditable run record, probably
  behind explicit review until confidence is high.

## Product Experience Notes

By the third round, the repetitive parts of dogfooding became the product spec: search online,
write a local markdown note, register it, remember the source ID, run ingest explicitly, query to
verify, then manually decide where synthesis should be updated. The path is safe and inspectable,
but too many decisions live in the user's head.

The web/search shell and CLI query are good inspection surfaces. The next UX gain is not cosmetic;
it is reducing the unstructured handoff between "new source exists" and "the wiki knows what to do
with it."
