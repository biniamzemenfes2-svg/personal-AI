"""Semantic long-term memory (embeddings + cosine similarity)."""
import json
import logging
import math
from datetime import datetime

log = logging.getLogger("aetheros.memory")


def cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    def __init__(self, db, client, embed_model: str):
        self.db = db
        self.client = client
        self.embed_model = embed_model

    def embed(self, text: str):
        try:
            resp = self.client.embeddings.create(input=[text], model=self.embed_model)
            return resp.data[0].embedding
        except Exception as e:
            log.error("Embedding failed: %s", e)
            return None

    def store(self, text: str) -> str:
        vector = self.embed(text)
        if not vector:
            return "Failed to process memory vector."
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO vector_memory (text, embedding, timestamp) VALUES (?, ?, ?)",
                (text, json.dumps(vector), datetime.now().isoformat()),
            )
        return "Memory permanently indexed."

    def search(self, query: str, top_k: int = 3, min_score: float = 0.35):
        query_vec = self.embed(query)
        if not query_vec:
            return []
        with self.db.connect() as conn:
            rows = conn.execute("SELECT text, embedding FROM vector_memory").fetchall()

        scored = []
        for text, emb_str in rows:
            try:
                emb = json.loads(emb_str)
            except (json.JSONDecodeError, TypeError):
                log.warning("Skipping malformed memory record")
                continue
            scored.append((text, cosine_similarity(query_vec, emb)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for t, s in scored[:top_k] if s > min_score]
