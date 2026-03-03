# Changelog

All notable changes to MindClaw will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
