"""
mindclaw.cli — Command-line interface for MindClaw.

Usage:
    mindclaw remember "We chose PostgreSQL for the backend"
    mindclaw recall "database decision"
    mindclaw list --category decision --limit 10
    mindclaw link <id1> <id2> --relation "depends_on"
    mindclaw graph <id> --depth 2
    mindclaw capture "conversation text here..."
    mindclaw stats
    mindclaw decay
    mindclaw export > backup.json
    mindclaw import backup.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from .capture import AutoCapture
from .graph import KnowledgeGraph
from .search import SearchEngine
from .store import Memory, MemoryStore


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_memory(mem: Memory, *, verbose: bool = False) -> str:
    """Format a memory for terminal display."""
    age = _human_time(time.time() - mem.created_at)
    stars = "★" * min(int(mem.importance * 5) + 1, 5)
    tags = ", ".join(mem.tags) if mem.tags else "—"

    lines = [
        f"  [{mem.id}] {stars}  {mem.category.upper()}",
        f"  {mem.content[:120]}",
    ]
    if mem.summary and mem.summary != mem.content and verbose:
        lines.append(f"  Summary: {mem.summary[:100]}")
    lines.append(f"  Tags: {tags}  |  Age: {age}  |  Accessed: {mem.access_count}x")
    if verbose:
        lines.append(f"  Source: {mem.source}  |  Importance: {mem.importance:.2f}")
    return "\n".join(lines)


def _human_time(seconds: float) -> str:
    """Convert seconds to human-readable time."""
    if seconds < 60:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 30:
        return f"{int(days)}d ago"
    months = days / 30
    return f"{int(months)}mo ago"


def _print_separator() -> None:
    print("─" * 60)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_remember(args: argparse.Namespace, store: MemoryStore) -> None:
    """Store a new memory."""
    mem = Memory(
        content=args.content,
        summary=args.summary or "",
        category=args.category or "note",
        tags=args.tags.split(",") if args.tags else [],
        source=args.source or "cli",
        importance=args.importance,
    )
    store.add(mem)
    print(f"✓ Remembered [{mem.id}]")
    print(_fmt_memory(mem))


def cmd_recall(args: argparse.Namespace, store: MemoryStore) -> None:
    """Search and recall memories."""
    engine = SearchEngine(store)
    engine.rebuild()
    results = engine.search(args.query, top_k=args.limit)

    if not results:
        print("No memories found matching your query.")
        return

    print(f"Found {len(results)} memories:\n")
    for i, r in enumerate(results, 1):
        mem = r["memory"]
        score = r["score"]
        print(f"  {i}. (score: {score:.3f})")
        print(_fmt_memory(mem, verbose=args.verbose))
        _print_separator()


def cmd_get(args: argparse.Namespace, store: MemoryStore) -> None:
    """Get a specific memory by ID."""
    mem = store.get(args.id)
    if mem is None:
        print(f"Memory [{args.id}] not found.")
        sys.exit(1)
    print(_fmt_memory(mem, verbose=True))

    # Show connected edges
    graph = KnowledgeGraph(store)
    neighbors = graph.neighbors(args.id, max_depth=1)
    if neighbors:
        print(f"\n  Connected to {len(neighbors)} memories:")
        for node in neighbors:
            print(f"    → [{node.memory.id}] {node.memory.content[:60]}")


def cmd_list(args: argparse.Namespace, store: MemoryStore) -> None:
    """List memories with filters."""
    memories = store.list_memories(
        category=args.category,
        tag=args.tag,
        include_archived=args.archived,
        limit=args.limit,
        order_by=args.sort,
    )

    if not memories:
        print("No memories found.")
        return

    print(f"Showing {len(memories)} memories:\n")
    for mem in memories:
        print(_fmt_memory(mem, verbose=args.verbose))
        _print_separator()


def cmd_forget(args: argparse.Namespace, store: MemoryStore) -> None:
    """Delete or archive a memory."""
    if args.hard:
        ok = store.delete(args.id)
        action = "Deleted"
    else:
        ok = store.archive(args.id)
        action = "Archived"

    if ok:
        print(f"✓ {action} [{args.id}]")
    else:
        print(f"Memory [{args.id}] not found.")
        sys.exit(1)


def cmd_link(args: argparse.Namespace, store: MemoryStore) -> None:
    """Create an edge between two memories."""
    graph = KnowledgeGraph(store)
    edge_ids = graph.link(
        args.source_id,
        args.target_id,
        args.relation,
        bidirectional=args.bidirectional,
    )
    print(f"✓ Linked [{args.source_id}] —({args.relation})→ [{args.target_id}]")
    if args.bidirectional:
        print(f"  (bidirectional, {len(edge_ids)} edges created)")


def cmd_graph(args: argparse.Namespace, store: MemoryStore) -> None:
    """Show the knowledge subgraph around a memory."""
    graph = KnowledgeGraph(store)
    sub = graph.subgraph(args.id, depth=args.depth)

    nodes = sub["nodes"]
    edges = sub["edges"]

    if not nodes:
        print(f"Memory [{args.id}] not found or has no connections.")
        return

    print(f"Subgraph around [{args.id}] (depth={args.depth}):\n")
    print(f"  Nodes ({len(nodes)}):")
    for n in nodes:
        marker = "●" if n["id"] == args.id else "○"
        print(f"    {marker} [{n['id']}] {n['label']}")

    if edges:
        print(f"\n  Edges ({len(edges)}):")
        for e in edges:
            print(f"    [{e['source']}] —({e['relation']})→ [{e['target']}]")

    if args.json:
        print(f"\nJSON:\n{json.dumps(sub, indent=2)}")


def cmd_capture(args: argparse.Namespace, store: MemoryStore) -> None:
    """Auto-capture memories from text."""
    # Read from argument or stdin
    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text()
    else:
        print("Reading from stdin (Ctrl+D to finish)...")
        text = sys.stdin.read()

    capture = AutoCapture(store)
    results = capture.process(text, source=args.source or "capture-cli", dry_run=args.dry_run)

    if not results:
        print("No capturable information detected.")
        return

    mode = "DETECTED (dry run)" if args.dry_run else "CAPTURED"
    print(f"{mode} {len(results)} memories:\n")
    for r in results:
        print(f"  [{r.rule_name}] (confidence: {r.confidence:.0%})")
        print(f"    {r.memory.content[:100]}")
        print(f"    Category: {r.memory.category} | Importance: {r.memory.importance:.1f}")
        _print_separator()


def cmd_stats(args: argparse.Namespace, store: MemoryStore) -> None:
    """Show memory store statistics."""
    s = store.stats()
    print("MindClaw Stats")
    print("═" * 40)
    print(f"  Total memories:  {s['total_memories']}")
    print(f"  Active:          {s['active']}")
    print(f"  Archived:        {s['archived']}")
    print(f"  Knowledge edges: {s['edges']}")
    print(f"  DB size:         {s['db_size_kb']} KB")
    print(f"  DB path:         {s['db_path']}")
    if s["categories"]:
        print(f"\n  Categories:")
        for cat, count in s["categories"].items():
            print(f"    {cat}: {count}")


def cmd_decay(args: argparse.Namespace, store: MemoryStore) -> None:
    """Apply decay to memory importance and archive stale memories."""
    threshold = args.threshold
    archived = store.apply_decay(threshold=threshold)
    print(f"✓ Decay applied. {archived} memories archived (below {threshold:.2f}).")


def cmd_export(args: argparse.Namespace, store: MemoryStore) -> None:
    """Export all memories to JSON."""
    data = store.export_json()
    if args.output:
        Path(args.output).write_text(data)
        print(f"✓ Exported to {args.output}")
    else:
        print(data)


def cmd_import(args: argparse.Namespace, store: MemoryStore) -> None:
    """Import memories from JSON file."""
    data = Path(args.file).read_text()
    result = store.import_json(data, merge=not args.replace)
    print(f"✓ Imported: {result['memories']} memories, {result['edges']} edges")
    if result["skipped"]:
        print(f"  Skipped {result['skipped']} duplicates")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mindclaw",
        description="MindClaw — Persistent memory & knowledge graph for AI agents.",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to SQLite database (default: ~/.mindclaw/memory.db)",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # remember
    p = sub.add_parser("remember", aliases=["r", "add"], help="Store a new memory")
    p.add_argument("content", help="The memory content")
    p.add_argument("-s", "--summary", help="Short summary")
    p.add_argument("-c", "--category", default="note",
                   help="Category: fact, decision, preference, error, note, todo")
    p.add_argument("-t", "--tags", help="Comma-separated tags")
    p.add_argument("--source", help="Source label")
    p.add_argument("-i", "--importance", type=float, default=0.6, help="0.0–1.0")

    # recall / search
    p = sub.add_parser("recall", aliases=["search", "q"], help="Search memories")
    p.add_argument("query", help="Search query")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.add_argument("-v", "--verbose", action="store_true")

    # get
    p = sub.add_parser("get", help="Get a memory by ID")
    p.add_argument("id", help="Memory ID")

    # list
    p = sub.add_parser("list", aliases=["ls"], help="List memories")
    p.add_argument("-c", "--category", help="Filter by category")
    p.add_argument("-t", "--tag", help="Filter by tag")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.add_argument("--sort", default="importance DESC",
                   help="Order: 'importance DESC', 'created_at DESC', etc.")
    p.add_argument("--archived", action="store_true", help="Include archived")
    p.add_argument("-v", "--verbose", action="store_true")

    # forget
    p = sub.add_parser("forget", aliases=["rm", "del"], help="Archive or delete a memory")
    p.add_argument("id", help="Memory ID to forget")
    p.add_argument("--hard", action="store_true", help="Hard delete (not just archive)")

    # link
    p = sub.add_parser("link", help="Link two memories")
    p.add_argument("source_id", help="Source memory ID")
    p.add_argument("target_id", help="Target memory ID")
    p.add_argument("-r", "--relation", default="related_to", help="Relation type")
    p.add_argument("-b", "--bidirectional", action="store_true")

    # graph
    p = sub.add_parser("graph", help="Show knowledge subgraph")
    p.add_argument("id", help="Center memory ID")
    p.add_argument("-d", "--depth", type=int, default=2)
    p.add_argument("--json", action="store_true", help="Output JSON")

    # capture
    p = sub.add_parser("capture", aliases=["cap"], help="Auto-capture from text")
    p.add_argument("text", nargs="?", help="Text to analyze")
    p.add_argument("-f", "--file", help="Read from file")
    p.add_argument("--source", help="Source label")
    p.add_argument("--dry-run", action="store_true", help="Detect without saving")

    # stats
    sub.add_parser("stats", help="Show memory statistics")

    # decay
    p = sub.add_parser("decay", help="Apply importance decay")
    p.add_argument("--threshold", type=float, default=0.05,
                   help="Archive below this importance")

    # export
    p = sub.add_parser("export", help="Export memories to JSON")
    p.add_argument("-o", "--output", help="Output file path")

    # import
    p = sub.add_parser("import", help="Import memories from JSON")
    p.add_argument("file", help="JSON file to import")
    p.add_argument("--replace", action="store_true",
                   help="Replace all (default: merge)")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_COMMANDS = {
    "remember": cmd_remember, "r": cmd_remember, "add": cmd_remember,
    "recall": cmd_recall, "search": cmd_recall, "q": cmd_recall,
    "get": cmd_get,
    "list": cmd_list, "ls": cmd_list,
    "forget": cmd_forget, "rm": cmd_forget, "del": cmd_forget,
    "link": cmd_link,
    "graph": cmd_graph,
    "capture": cmd_capture, "cap": cmd_capture,
    "stats": cmd_stats,
    "decay": cmd_decay,
    "export": cmd_export,
    "import": cmd_import,
}


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    store = MemoryStore(db_path=args.db)
    handler = _COMMANDS.get(args.command)

    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        handler(args, store)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
