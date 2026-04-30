# Round 2: Context Engineering and Repository Memory

Source URLs:

- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://openai.com/index/harness-engineering/
- https://openai.com/solutions/blueprints/knowledge-retrieval/

## Source Note

This round tests whether Splendor's LLM Wiki framing connects to broader agent engineering
practice. The answer is yes: recent agent guidance treats context as a scarce resource, recommends
structured persistent notes for long-horizon work, and increasingly treats repository knowledge as
the system of record instead of putting all guidance into one giant instruction file.

## Core Claims

- Context engineering reframes prompt work as selecting and maintaining the right information for
  each inference step. The important object is not only the prompt; it is the whole context state.
- Long-horizon agents need externalized memory. Durable notes, task files, planning state, and
  compiled wiki pages let an agent resume work without carrying the entire conversation forward.
- Repository knowledge should be progressively disclosed. A short instruction file should map to
  deeper docs and wiki pages rather than trying to contain everything directly.
- Retrieval remains valuable, but retrieval-only systems answer from documents more than they
  maintain a project memory. Splendor's opportunity is to pair retrieval with durable synthesis,
  review state, and planning artifacts.
- Citations, evals, and groundedness checks matter even for local-first tools. Splendor's lint,
  health, provenance links, and source manifests are the beginnings of a trust layer.

## Design Implications

Splendor is best described as context infrastructure for agents and humans working in a repository:

- `AGENTS.md` is the thin entry point.
- `docs/`, `wiki/`, and `planning/` hold durable working memory.
- `state/` records what the tool did and what remains pending.
- `splendor query` is the context-selection path.
- `splendor file-answer` and future compile/update commands are the persistence path.

The product should make this loop more explicit in documentation and UI. A user should be able to
ask "what do I need to know before continuing this project?" and get a compact, source-linked
orientation assembled from wiki, planning, and recent runs.

## Product Experience Notes

The current `--no-save` query option is valuable during dogfooding because it lets exploration stay
non-mutating until a result is worth filing. Query output also makes review state and provenance
visible, which is exactly the trust signal these external sources emphasize.

The missing feature is context assembly. Search results are useful, but users still need to manually
open several pages and infer the working state. Splendor should eventually have a briefing command
that returns the highest-signal project memory for a goal, including source-backed knowledge,
active planning records, and stale or contested areas.
