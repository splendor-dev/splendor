# Lucas Astorian LLM Wiki Implementation

Source URL: https://github.com/lucasastorian/llmwiki

## Source Note

`lucasastorian/llmwiki` is an open-source implementation of Karpathy's LLM Wiki pattern. Its README
frames the system as a way to point at a research folder, run a local app, connect Claude through
MCP, and let the agent write and maintain wiki pages with links and citations.

## Implementation Pattern

The project keeps source files in place, creates a `wiki/` directory for generated pages, and keeps
a hidden local index/cache that can be rebuilt. Its architecture combines a web frontend, a FastAPI
backend, a local SQLite index, an MCP server, and filesystem-backed source material.

Claude-facing tools include guide, search, read, write, and delete operations. The system positions
the filesystem as the source of truth while using SQLite as derived search/index infrastructure.

## Useful Contrasts with Splendor

- LLM Wiki emphasizes MCP tool access for Claude; Splendor currently emphasizes deterministic CLI
  commands that agents and humans can both run.
- LLM Wiki uses SQLite as a local derived index; Splendor currently avoids hidden caches and keeps
  machine-readable state in tracked files.
- LLM Wiki includes a fuller web app; Splendor's first web UI is intentionally read-only and
  non-essential.
- Both systems share the same core premise: raw sources should remain stable while the wiki evolves
  as a maintained synthesis layer.

## Product Lessons

The implementation validates that a local web UI is useful even when the canonical state is a
filesystem of markdown and JSON records. It also shows that agent-facing tools need clear operating
conventions, not only storage primitives.
