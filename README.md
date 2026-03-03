# MindClaw

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-0.1.0-green.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/interface-CLI-black.svg)](#command-reference)
[![ClawHub](https://img.shields.io/badge/clawhub.ai-ready-blueviolet.svg)](https://clawhub.ai)

> **Remember everything, forget nothing.**

Persistent memory and knowledge graph for AI agents.

MindClaw is an OpenClaw-ready memory tool that gives agents long-term recall across sessions. It stores facts, decisions, preferences, and errors; links related memories into a graph; and supports capture/search/export workflows from the command line.

## Features

- Persistent memory store in SQLite
- Retrieval by recall/search command flow
- Knowledge graph relations between memories
- Auto-capture from raw text, files, and stdin
- Archiving/decay lifecycle for memory hygiene
- JSON export/import for backup and portability

## Installation

### Requirements

- Python 3.10+

### Install locally

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[semantic]"
pip install -e ".[dev]"
```

## Quickstart

```bash
mindclaw remember "Decidimos usar PostgreSQL para producción" -c decision -t backend,db
mindclaw recall "postgresql decision" -n 5
mindclaw list --sort "importance DESC" -n 10
mindclaw stats
```

## Command Reference

| Command | Aliases | Purpose | Example |
|---|---|---|---|
| `remember` | `r`, `add` | Save a new memory | `mindclaw remember "texto" -c note -t tag1,tag2 -i 0.6` |
| `recall` | `search`, `q` | Search memories | `mindclaw recall "query" -n 10 -v` |
| `get` | — | Fetch one memory by ID | `mindclaw get <id>` |
| `list` | `ls` | List memories with filters | `mindclaw list -c decision -t backend --sort "created_at DESC"` |
| `forget` | `rm`, `del` | Archive or hard-delete | `mindclaw forget <id> --hard` |
| `link` | — | Create graph relation | `mindclaw link <source_id> <target_id> -r depends_on -b` |
| `graph` | — | Show connected subgraph | `mindclaw graph <id> -d 2 --json` |
| `capture` | `cap` | Extract memories from text | `mindclaw capture -f ./conversation.txt --dry-run` |
| `stats` | — | Show DB/store stats | `mindclaw stats` |
| `decay` | — | Apply decay + archive weak memories | `mindclaw decay --threshold 0.05` |
| `export` | — | Export all data to JSON | `mindclaw export -o backup.json` |
| `import` | — | Import JSON backup | `mindclaw import backup.json --replace` |

## Agent Integration (OpenClaw Pattern)

Recommended loop for an agent runtime:

1. Persist key outcomes with `remember`
2. Retrieve context before planning with `recall`
3. Connect related facts using `link`
4. Extract structured memory from logs/chats using `capture`
5. Run maintenance (`decay`) and backups (`export`) periodically

Example flow:

```bash
mindclaw remember "El usuario prefiere respuestas en español" -c preference -t language,ux --source agent
mindclaw recall "preferencias del usuario idioma" -n 5
mindclaw capture "Error 502 en webhook; probable timeout upstream" --source logs
mindclaw export -o backup.json
```

## Architecture

Core modules:

- `store.py`: SQLite persistence, memory CRUD, stats, import/export, decay
- `search.py`: indexing + retrieval logic
- `graph.py`: relationships and subgraph traversal
- `capture.py`: rule-based extraction from free text
- `cli.py`: command parser + command handlers

High-level flow:

```text
CLI command
   ↓
Parser/handler (cli.py)
   ↓
Store/Search/Graph/Capture modules
   ↓
SQLite memory database
```

## Configuration

| Setting | Default | Override |
|---|---|---|
| DB path | `~/.mindclaw/memory.db` | `--db <path>` flag or `MINDCLAW_DB` env var |

```bash
# flag
mindclaw --db ./data/memory.db stats

# env var
export MINDCLAW_DB=./data/memory.db
mindclaw stats
```

## Publishing to ClawHub

MindClaw ships with a [`clawhub.yaml`](clawhub.yaml) manifest that declares capabilities, config, and metadata for [clawhub.ai](https://clawhub.ai).

To publish:

1. Bump version in `pyproject.toml`, `clawhub.yaml`, and `src/mindclaw/__init__.py`
2. Update [`CHANGELOG.md`](CHANGELOG.md)
3. Tag: `git tag v0.x.x`
4. Push: `git push origin main --tags`
5. ClawHub picks up the release automatically from the tag

The manifest exposes all 12 CLI commands as agent-consumable capabilities, so any OpenClaw-compatible runtime can discover and invoke them.

## Programmatic usage

MindClaw can also be used as a Python library:

```python
from mindclaw.store import MemoryStore, Memory

store = MemoryStore(db_path="./my_agent.db")

# Create
mem = Memory(content="User prefers dark mode", category="preference", tags=["ui"])
store.add(mem)

# Search
from mindclaw.search import SearchEngine
engine = SearchEngine(store)
engine.rebuild()
results = engine.search("dark mode", top_k=5)

# Graph
from mindclaw.graph import KnowledgeGraph
graph = KnowledgeGraph(store)
graph.link(mem.id, other_id, "related_to")
sub = graph.subgraph(mem.id, depth=2)

# Auto-capture
from mindclaw.capture import AutoCapture
capture = AutoCapture(store)
captured = capture.process("Meeting notes: deploy v2 Friday", source="agent")
```

## Project Structure

```text
.
├── pyproject.toml          # Package metadata & dependencies
├── clawhub.yaml            # ClawHub registry manifest
├── README.md
├── CONTRIBUTING.md         # Contribution guide
├── CHANGELOG.md            # Version history
├── LICENSE                 # MIT
└── src/
    └── mindclaw/
        ├── __init__.py     # Version & package init
        ├── capture.py      # Auto-extraction from text
        ├── cli.py          # CLI parser & command handlers
        ├── graph.py        # Knowledge graph (edges, subgraph)
        ├── search.py       # Search/recall engine
        └── store.py        # SQLite memory store
```

## Roadmap

- [ ] MCP (Model Context Protocol) server mode
- [ ] Semantic search with local embeddings
- [ ] Web dashboard for memory visualization
- [ ] Multi-agent shared memory (namespaces)
- [ ] Plugin system for custom capture rules
- [ ] ClawHub verified badge

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, branching, and PR guidelines.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## License

MIT — see [`LICENSE`](LICENSE) for details.