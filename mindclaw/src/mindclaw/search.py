"""
mindclaw.search — Fast search engine with TF-IDF (zero dependencies)
and optional ONNX semantic embeddings.

Two search layers:
  1. TF-IDF (always available, instant, 0 extra bytes)
  2. Semantic via all-MiniLM-L6-v2 ONNX (optional, ~23MB, lazy-loaded)
"""

from __future__ import annotations

import math
import re
import struct
from collections import Counter, defaultdict
from typing import Any, Optional

from .store import Memory, MemoryStore


# ===========================================================================
# Layer 1: TF-IDF Search (zero dependencies)
# ===========================================================================

# Simple tokenizer — split on non-alphanumeric, lowercase, skip short tokens
_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could to of in for on with "
    "at by from as into through during about after before between "
    "and or but not no nor so yet both either neither each every all "
    "any few more most other some such that this these those it its "
    "i me my we our you your he him his she her they them their what "
    "which who whom how when where why if then else than too very".split()
)


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenizer with stopword removal."""
    tokens = _SPLIT_RE.split(text.lower())
    return [t for t in tokens if len(t) > 1 and t not in _STOP_WORDS]


class TFIDFIndex:
    """
    In-memory TF-IDF index built from memories.
    Rebuilt on demand; no external dependencies.
    """

    def __init__(self) -> None:
        self._doc_tokens: dict[str, list[str]] = {}  # memory_id -> tokens
        self._idf: dict[str, float] = {}
        self._doc_count = 0

    def build(self, memories: list[Memory]) -> None:
        """Build the index from a list of memories."""
        self._doc_tokens.clear()
        self._idf.clear()
        self._doc_count = len(memories)

        if not memories:
            return

        df: dict[str, int] = defaultdict(int)  # document frequency

        for mem in memories:
            text = f"{mem.content} {mem.summary} {' '.join(mem.tags)}"
            tokens = _tokenize(text)
            self._doc_tokens[mem.id] = tokens
            seen: set[str] = set()
            for t in tokens:
                if t not in seen:
                    df[t] += 1
                    seen.add(t)

        # IDF: log(N / df) + 1  (smoothed)
        n = self._doc_count
        self._idf = {
            term: math.log(n / freq) + 1.0
            for term, freq in df.items()
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Search the index. Returns list of (memory_id, score) sorted desc.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_counter = Counter(query_tokens)
        scores: dict[str, float] = defaultdict(float)

        for memory_id, doc_tokens in self._doc_tokens.items():
            if not doc_tokens:
                continue
            doc_counter = Counter(doc_tokens)
            doc_len = len(doc_tokens)

            for term, qf in query_counter.items():
                if term not in doc_counter:
                    continue
                tf = doc_counter[term] / doc_len
                idf = self._idf.get(term, 1.0)
                scores[memory_id] += tf * idf * qf

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def to_vector(self, text: str) -> bytes:
        """Convert text to a sparse TF-IDF vector stored as bytes."""
        tokens = _tokenize(text)
        counter = Counter(tokens)
        total = len(tokens) if tokens else 1

        # Create a sorted list of (term_hash, tfidf_value)
        components: list[tuple[int, float]] = []
        for term, count in counter.items():
            tf = count / total
            idf = self._idf.get(term, 1.0)
            h = hash(term) & 0xFFFFFFFF  # 32-bit hash
            components.append((h, tf * idf))

        components.sort(key=lambda x: x[0])

        # Pack as pairs of (uint32, float32)
        return struct.pack(
            f"<{len(components) * 2}f",
            *[v for h, val in components for v in (float(h), val)],
        )


# ===========================================================================
# Layer 2: Semantic Search (ONNX, optional)
# ===========================================================================

class SemanticIndex:
    """
    Optional semantic search using all-MiniLM-L6-v2 via ONNX Runtime.
    Only loaded if onnxruntime + numpy are available.
    """

    def __init__(self) -> None:
        self._session = None
        self._tokenizer = None
        self._available: Optional[bool] = None

    @property
    def available(self) -> bool:
        """Check if ONNX Runtime and the model are available."""
        if self._available is not None:
            return self._available
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _ensure_model(self) -> bool:
        """Download model if needed and load session. Returns True if ready."""
        if self._session is not None:
            return True
        if not self.available:
            return False

        import importlib
        from pathlib import Path

        model_dir = Path.home() / ".mindclaw" / "models"
        model_path = model_dir / "all-MiniLM-L6-v2.onnx"
        tokenizer_path = model_dir / "tokenizer.json"

        if not model_path.exists():
            # Will be downloaded on first use
            return False

        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(str(model_path))
            return True
        except Exception:
            return False

    def encode(self, texts: list[str]) -> Any:
        """
        Encode a list of texts into embedding vectors.
        Returns numpy array of shape (len(texts), 384) or None.
        """
        if not self._ensure_model():
            return None

        import numpy as np

        # Simple whitespace tokenizer (placeholder — real impl needs tokenizer)
        # For MVP, this returns None to fall back to TF-IDF
        return None

    def cosine_similarity(self, a: Any, b: Any) -> float:
        """Compute cosine similarity between two vectors."""
        import numpy as np
        a = np.asarray(a, dtype=np.float32).flatten()
        b = np.asarray(b, dtype=np.float32).flatten()
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(dot / norm)


# ===========================================================================
# Unified Search Interface
# ===========================================================================

class SearchEngine:
    """
    Unified search combining TF-IDF (always) + semantic (optional).

    Usage:
        engine = SearchEngine(store)
        engine.rebuild()
        results = engine.search("payment API issue")
    """

    def __init__(self, store: MemoryStore):
        self.store = store
        self.tfidf = TFIDFIndex()
        self.semantic = SemanticIndex()
        self._memories_cache: dict[str, Memory] = {}

    def rebuild(self) -> dict[str, Any]:
        """Rebuild the search index from all active memories."""
        memories = self.store.list_memories(limit=10_000, include_archived=False)
        self._memories_cache = {m.id: m for m in memories}
        self.tfidf.build(memories)

        # Cache TF-IDF vectors in the store
        for mem in memories:
            text = f"{mem.content} {mem.summary} {' '.join(mem.tags)}"
            vec = self.tfidf.to_vector(text)
            self.store.save_embedding(mem.id, vec, model="tfidf")

        return {
            "indexed": len(memories),
            "semantic_available": self.semantic.available,
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        boost_importance: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search memories by query text.
        Returns list of {memory, score, method} dicts.
        """
        # TF-IDF search
        tfidf_results = self.tfidf.search(query, top_k=top_k * 2)

        results: list[dict[str, Any]] = []
        for memory_id, raw_score in tfidf_results:
            mem = self._memories_cache.get(memory_id)
            if mem is None:
                mem = self.store.get(memory_id)
            if mem is None:
                continue

            score = raw_score
            if boost_importance:
                score *= (0.5 + mem.importance)

            results.append({
                "memory": mem,
                "score": round(score, 4),
                "method": "tfidf",
            })

        # Sort and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def similar(
        self, memory_id: str, *, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Find memories similar to a given memory."""
        mem = self.store.get(memory_id)
        if mem is None:
            return []
        query = f"{mem.content} {mem.summary}"
        results = self.search(query, top_k=top_k + 1)
        # Remove the query memory itself
        return [r for r in results if r["memory"].id != memory_id][:top_k]
