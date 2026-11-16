"""Long-term semantic memory: embeddings, similarity + recency + importance ranking, dedupe."""
import json
import logging
import math
from datetime import datetime

import config

log = logging.getLogger("aetheros.memory")

MSG_STORED = "Memory permanently indexed."
MSG_DUPLICATE = "Memory already known; refreshed it."
MSG_FAILED = "Failed to process memory vector."


def cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    def __init__(self, db, client, embed_model: str, now=None):
        self.db = db
        self.client = client
        self.embed_model = embed_model
        self._now = now or datetime.now  # injectable clock for tests

    def embed(self, text: str):
        try:
            resp = self.client.embeddings.create(input=[text], model=self.embed_model)
            return resp.data[0].embedding
        except Exception as e:
            log.error("Embedding failed: %s", e)
            return None

    def _load(self, conn):
        """All usable memory rows as dicts; malformed embeddings are skipped."""
        rows = conn.execute(
            "SELECT id, text, embedding, timestamp, importance, kind, access_count FROM vector_memory"
        ).fetchall()
        out = []
        for id_, text, emb_str, ts, imp, kind, count in rows:
            try:
                emb = json.loads(emb_str)
                if not isinstance(emb, list) or not emb:
                    raise ValueError("not a vector")
            except (json.JSONDecodeError, TypeError, ValueError):
                log.warning("Skipping malformed memory record %s", id_)
                continue
            out.append({"id": id_, "text": text, "emb": emb, "ts": ts,
                        "importance": 0.5 if imp is None else imp,
                        "kind": kind or "event", "count": count or 0})
        return out

    def _recency(self, ts) -> float:
        """1.0 for brand new, halving every MEMORY_HALF_LIFE_DAYS; neutral 0.5 if unparseable."""
        try:
            age_days = max(0.0, (self._now() - datetime.fromisoformat(ts)).total_seconds() / 86400)
        except (TypeError, ValueError):
            return 0.5
        return 0.5 ** (age_days / config.MEMORY_HALF_LIFE_DAYS)

    def store(self, text: str, importance: float = 0.5, kind: str = "event") -> str:
        """Save a memory. Near-duplicates of the same kind are merged (refreshed) instead of added."""
        text = (text or "").strip()
        if not text:
            return MSG_FAILED
        vector = self.embed(text)
        if not vector:
            return MSG_FAILED
        importance = min(1.0, max(0.0, importance))
        now = self._now().isoformat()

        with self.db.connect() as conn:
            best = None
            for r in self._load(conn):
                if r["kind"] != kind or len(r["emb"]) != len(vector):
                    continue
                sim = cosine_similarity(vector, r["emb"])
                if sim >= config.MEMORY_DEDUPE_THRESHOLD and (best is None or sim > best[0]):
                    best = (sim, r)
            if best:
                existing = best[1]
                conn.execute("UPDATE vector_memory SET timestamp=?, importance=? WHERE id=?",
                             (now, max(existing["importance"], importance), existing["id"]))
                return MSG_DUPLICATE
            conn.execute(
                "INSERT INTO vector_memory (text, embedding, timestamp, importance, kind) "
                "VALUES (?, ?, ?, ?, ?)",
                (text, json.dumps(vector), now, importance, kind))
        return MSG_STORED

    def search(self, query: str, top_k: int = 3, min_score: float = 0.35):
        """Relevance gate on similarity, then rank by similarity + recency + importance."""
        query_vec = self.embed(query)
        if not query_vec:
            return []
        with self.db.connect() as conn:
            rows = self._load(conn)

        ranked = []
        for r in rows:
            if len(r["emb"]) != len(query_vec):
                continue
            sim = cosine_similarity(query_vec, r["emb"])
            if sim <= min_score:
                continue
            score = (config.MEMORY_WEIGHT_SIMILARITY * sim
                     + config.MEMORY_WEIGHT_RECENCY * self._recency(r["ts"])
                     + config.MEMORY_WEIGHT_IMPORTANCE * r["importance"])
            ranked.append((score, r))
        ranked.sort(key=lambda x: x[0], reverse=True)
        top = [r for _, r in ranked[:top_k]]

        if top:
            now = self._now().isoformat()
            with self.db.connect() as conn:
                conn.executemany(
                    "UPDATE vector_memory SET last_accessed=?, access_count=COALESCE(access_count,0)+1 WHERE id=?",
                    [(now, r["id"]) for r in top])
        return [r["text"] for r in top]

    def list(self, limit: int = 50):
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, text, kind, importance, timestamp FROM vector_memory "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "text": r[1], "kind": r[2] or "event",
                 "importance": 0.5 if r[3] is None else r[3], "timestamp": r[4]} for r in rows]

    def delete(self, memory_id: int) -> str:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM vector_memory WHERE id=?", (memory_id,))
        if not cur.rowcount:
            raise LookupError(f"No memory #{memory_id}.")
        return f"Memory #{memory_id} forgotten."
