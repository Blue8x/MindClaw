"""
mindclaw.store — SQLite-backed persistent memory store.

Stores memories as structured records with metadata, timestamps,
importance scores, and access tracking for decay/relevance.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Generator, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Memory:
    """A single memory record."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str = ""
    summary: str = ""
    category: str = "general"          # fact, decision, preference, error, note
    tags: list[str] = field(default_factory=list)
    source: str = ""                   # where this memory was captured
    importance: float = 0.5            # 0.0 – 1.0
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    decay_rate: float = 0.01           # how fast importance decays
    archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tags"] = json.dumps(d["tags"])
        d["metadata"] = json.dumps(d["metadata"])
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Memory":
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        d["metadata"] = json.loads(d["metadata"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    summary         TEXT DEFAULT '',
    category        TEXT DEFAULT 'general',
    tags            TEXT DEFAULT '[]',
    source          TEXT DEFAULT '',
    importance      REAL DEFAULT 0.5,
    access_count    INTEGER DEFAULT 0,
    created_at      REAL,
    last_accessed   REAL,
    updated_at      REAL,
    decay_rate      REAL DEFAULT 0.01,
    archived        INTEGER DEFAULT 0,
    metadata        TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);

CREATE TABLE IF NOT EXISTS edges (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    relation        TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    created_at      REAL,
    metadata        TEXT DEFAULT '{}',
    FOREIGN KEY (source_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

CREATE TABLE IF NOT EXISTS embeddings_cache (
    memory_id       TEXT PRIMARY KEY,
    vector          BLOB NOT NULL,
    model           TEXT DEFAULT 'tfidf',
    updated_at      REAL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);
"""


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStore:
    """SQLite-backed persistent memory store with knowledge graph edges."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path.home() / ".mindclaw" / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # -- connection helpers -------------------------------------------------

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # -- CRUD ---------------------------------------------------------------

    def add(self, memory: Memory) -> Memory:
        """Insert a new memory. Returns the memory with its id."""
        with self._conn() as conn:
            d = memory.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT INTO memories ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by id, updating access stats."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, "
                "last_accessed = ? WHERE id = ?",
                (time.time(), memory_id),
            )
            return Memory.from_row(row)

    def update(self, memory_id: str, **kwargs: Any) -> Optional[Memory]:
        """Update fields of an existing memory."""
        if not kwargs:
            return self.get(memory_id)

        kwargs["updated_at"] = time.time()

        # Serialize complex fields
        if "tags" in kwargs:
            kwargs["tags"] = json.dumps(kwargs["tags"])
        if "metadata" in kwargs:
            kwargs["metadata"] = json.dumps(kwargs["metadata"])

        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [memory_id]

        with self._conn() as conn:
            conn.execute(
                f"UPDATE memories SET {sets} WHERE id = ?", vals
            )
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Hard-delete a memory and its edges."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cur.rowcount > 0

    def archive(self, memory_id: str) -> bool:
        """Soft-archive a memory (mark as archived, not deleted)."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memories SET archived = 1, updated_at = ? WHERE id = ?",
                (time.time(), memory_id),
            )
            return cur.rowcount > 0

    # -- Queries ------------------------------------------------------------

    def list_memories(
        self,
        *,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "importance DESC",
    ) -> list[Memory]:
        """List memories with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if not include_archived:
            clauses.append("archived = 0")
        if category:
            clauses.append("category = ?")
            params.append(category)
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")

        where = " AND ".join(clauses) if clauses else "1=1"
        allowed_orders = {
            "importance DESC", "importance ASC",
            "created_at DESC", "created_at ASC",
            "last_accessed DESC", "last_accessed ASC",
            "access_count DESC", "access_count ASC",
        }
        if order_by not in allowed_orders:
            order_by = "importance DESC"

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE {where} "
                f"ORDER BY {order_by} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        return [Memory.from_row(r) for r in rows]

    def search_text(self, query: str, *, limit: int = 20) -> list[Memory]:
        """Simple LIKE-based text search across content and summary."""
        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE archived = 0 AND "
                "(content LIKE ? OR summary LIKE ? OR tags LIKE ?) "
                "ORDER BY importance DESC LIMIT ?",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [Memory.from_row(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the memory store."""
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM memories"
            ).fetchone()["c"]
            active = conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE archived = 0"
            ).fetchone()["c"]
            archived = total - active
            categories = conn.execute(
                "SELECT category, COUNT(*) AS c FROM memories "
                "WHERE archived = 0 GROUP BY category ORDER BY c DESC"
            ).fetchall()
            edges_count = conn.execute(
                "SELECT COUNT(*) AS c FROM edges"
            ).fetchone()["c"]
        return {
            "total_memories": total,
            "active": active,
            "archived": archived,
            "edges": edges_count,
            "categories": {r["category"]: r["c"] for r in categories},
            "db_path": str(self.db_path),
            "db_size_kb": round(self.db_path.stat().st_size / 1024, 1)
            if self.db_path.exists()
            else 0,
        }

    # -- Knowledge Graph Edges ----------------------------------------------

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a directed edge between two memories."""
        edge_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO edges (id, source_id, target_id, relation, weight, "
                "created_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    edge_id,
                    source_id,
                    target_id,
                    relation,
                    weight,
                    time.time(),
                    json.dumps(metadata or {}),
                ),
            )
        return edge_id

    def get_edges(
        self, memory_id: str, *, direction: str = "both"
    ) -> list[dict[str, Any]]:
        """Get edges connected to a memory. direction: out, in, both."""
        results: list[dict[str, Any]] = []
        with self._conn() as conn:
            if direction in ("out", "both"):
                rows = conn.execute(
                    "SELECT * FROM edges WHERE source_id = ?", (memory_id,)
                ).fetchall()
                results.extend(dict(r) for r in rows)
            if direction in ("in", "both"):
                rows = conn.execute(
                    "SELECT * FROM edges WHERE target_id = ?", (memory_id,)
                ).fetchall()
                results.extend(dict(r) for r in rows)
        return results

    def remove_edge(self, edge_id: str) -> bool:
        """Delete an edge by id."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
            return cur.rowcount > 0

    # -- Embeddings Cache ---------------------------------------------------

    def save_embedding(
        self, memory_id: str, vector: bytes, model: str = "tfidf"
    ) -> None:
        """Cache an embedding vector for a memory."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings_cache "
                "(memory_id, vector, model, updated_at) VALUES (?, ?, ?, ?)",
                (memory_id, vector, model, time.time()),
            )

    def get_embedding(self, memory_id: str) -> Optional[tuple[bytes, str]]:
        """Retrieve cached embedding. Returns (vector_bytes, model) or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT vector, model FROM embeddings_cache WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        return (row["vector"], row["model"])

    def get_all_embeddings(self, model: str = "tfidf") -> list[tuple[str, bytes]]:
        """Return all (memory_id, vector) pairs for a given model."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT memory_id, vector FROM embeddings_cache WHERE model = ?",
                (model,),
            ).fetchall()
        return [(r["memory_id"], r["vector"]) for r in rows]

    # -- Maintenance --------------------------------------------------------

    def apply_decay(self, *, threshold: float = 0.05) -> int:
        """
        Decay importance of memories based on time since last access.
        Archives memories that fall below threshold.
        Returns count of archived memories.
        """
        now = time.time()
        archived_count = 0
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, importance, decay_rate, last_accessed "
                "FROM memories WHERE archived = 0"
            ).fetchall()
            for r in rows:
                days_since = (now - r["last_accessed"]) / 86400
                new_importance = r["importance"] * (1 - r["decay_rate"]) ** days_since
                if new_importance < threshold:
                    conn.execute(
                        "UPDATE memories SET archived = 1, importance = ?, "
                        "updated_at = ? WHERE id = ?",
                        (new_importance, now, r["id"]),
                    )
                    archived_count += 1
                elif abs(new_importance - r["importance"]) > 0.001:
                    conn.execute(
                        "UPDATE memories SET importance = ?, updated_at = ? "
                        "WHERE id = ?",
                        (new_importance, now, r["id"]),
                    )
        return archived_count

    def export_json(self) -> str:
        """Export entire memory store as JSON string."""
        with self._conn() as conn:
            memories = conn.execute("SELECT * FROM memories").fetchall()
            edges = conn.execute("SELECT * FROM edges").fetchall()
        return json.dumps(
            {
                "version": "0.1.0",
                "exported_at": time.time(),
                "memories": [dict(r) for r in memories],
                "edges": [dict(r) for r in edges],
            },
            indent=2,
        )

    def import_json(self, data: str, *, merge: bool = True) -> dict[str, int]:
        """
        Import memories and edges from JSON string.
        If merge=True, skip existing ids. If False, replace all.
        """
        payload = json.loads(data)
        imported = {"memories": 0, "edges": 0, "skipped": 0}

        with self._conn() as conn:
            if not merge:
                conn.execute("DELETE FROM edges")
                conn.execute("DELETE FROM memories")
                conn.execute("DELETE FROM embeddings_cache")

            for m in payload.get("memories", []):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO memories "
                        "(id, content, summary, category, tags, source, "
                        "importance, access_count, created_at, last_accessed, "
                        "updated_at, decay_rate, archived, metadata) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            m["id"], m["content"], m.get("summary", ""),
                            m.get("category", "general"),
                            m.get("tags", "[]"), m.get("source", ""),
                            m.get("importance", 0.5), m.get("access_count", 0),
                            m.get("created_at", time.time()),
                            m.get("last_accessed", time.time()),
                            m.get("updated_at", time.time()),
                            m.get("decay_rate", 0.01),
                            m.get("archived", 0),
                            m.get("metadata", "{}"),
                        ),
                    )
                    imported["memories"] += 1
                except sqlite3.IntegrityError:
                    imported["skipped"] += 1

            for e in payload.get("edges", []):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO edges "
                        "(id, source_id, target_id, relation, weight, "
                        "created_at, metadata) VALUES (?,?,?,?,?,?,?)",
                        (
                            e["id"], e["source_id"], e["target_id"],
                            e["relation"], e.get("weight", 1.0),
                            e.get("created_at", time.time()),
                            e.get("metadata", "{}"),
                        ),
                    )
                    imported["edges"] += 1
                except sqlite3.IntegrityError:
                    imported["skipped"] += 1

        return imported
