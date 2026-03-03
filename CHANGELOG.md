# Changelog

All notable changes to MindClaw will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-03-03

### Added

- **OpenClaw Markdown bridge** — full bidirectional integration with OpenClaw's native memory:
  - `mindclaw sync` — exports memories to `~/.openclaw/workspace/MEMORY.md` in-place;
    preserves all other content the agent has written to the file
  - `mindclaw md-import <file>` — imports bullet points from any OpenClaw `MEMORY.md` or
    `memory/YYYY-MM-DD.md` daily log; detects category from headings; deduplicates automatically
  - `MINDCLAW_OPENCLAW_WORKSPACE` env var for custom workspace path
  - Two new MCP tools: `sync_openclaw` and `import_markdown`
- **BM25 search** (replaces TF-IDF) — proper Okapi BM25 with IDF saturation and document-length
  normalisation; mirrors the BM25 layer in OpenClaw's hybrid search pipeline
- **Ollama semantic embeddings** — zero new dependencies (pure `urllib`); auto-detects a running
  Ollama instance and uses `nomic-embed-text` for cosine similarity; blended 70% BM25 + 30% semantic
- **Temporal decay at query time** (`--decay` flag on `recall`) — `score × e^(−λ × ageInDays)`
  with configurable `--halflife`; pinned memories are exempt; same formula as OpenClaw
- **MMR diversity re-ranking** (`--mmr` flag on `recall`) — Maximal Marginal Relevance reduces
  near-duplicate results; `--mmr-lambda` controls relevance/diversity trade-off (default 0.7)
- `recall` now shows which search method and options were used in the result header

### Changed

- `SearchEngine.rebuild()` now stores `model="bm25"` in embeddings cache (was `"tfidf"`)
- `SearchEngine` exposes `.ollama` (OllamaEmbedder) attribute; `.tfidf` is kept as alias to `.bm25`
- `clawhub.yaml`: version 0.3.0; added `openclaw:` integration block; new `sync` and `md-import`
  capabilities; `MINDCLAW_OPENCLAW_WORKSPACE` config entry


### Added

- **MCP Server** (`mcp_server.py`): Full Model Context Protocol server exposing all tools
  as native MCP tools for Claude Desktop, OpenClaw, and any MCP-compatible runtime
- `mindclaw mcp install` — one command to register with Claude Desktop or OpenClaw
- `mindclaw-mcp` script entry point for direct stdio server execution
- **Agent namespaces** (`--agent <name>`): scope all memory operations to a named agent
- **Pinned memories** (`--pin` flag, `pin` / `unpin` commands): memories that never decay
- **Memory confirmation** (`confirm <id>`): reinforce a memory, boosts importance ×confirmed
- **Conflict detection**: `remember` warns when new content may contradict existing memories
- **Timeline** (`timeline --hours 24`): chronological view of recent memories
- **Context window builder** (`context.py`): token-aware memory block for LLM prompt injection
- `context` CLI command with `--format markdown|plain|xml` and `--max-tokens`
- `conflicts` command: check any text against the store before storing
- `consolidate` command: merge near-duplicate memories automatically
- `stats` now shows pinned count and per-agent breakdowns
- `decay` now respects pinned flag and supports `--agent` scope
- `list` now supports `--pinned` flag
- Auto schema migration for databases created with v0.1.0
- `mcp` optional dependency group; `all` extra installs everything

### Changed

- `Memory` dataclass: new fields `agent_id`, `pinned`, `confirmed_count`
- `store.archive()` refuses to archive pinned memories
- `store.apply_decay()` skips pinned memories

## [0.1.0] — 2026-03-02

### Added

- Core memory store with SQLite backend (`store.py`)
- Search engine for memory recall (`search.py`)
- Knowledge graph with relations and subgraph traversal (`graph.py`)
- Auto-capture from free text, files, and stdin (`capture.py`)
- Full CLI with 12 commands: remember, recall, get, list, forget, link, graph, capture, stats, decay, export, import
- Memory categories: fact, decision, preference, error, note, todo
- Importance scoring and decay lifecycle
- JSON export/import for backup and portability
- Optional semantic search extras (onnxruntime + numpy)
- ClawHub manifest (`clawhub.yaml`) for registry compatibility

### Notes

- Initial alpha release
- Zero external dependencies for core functionality
