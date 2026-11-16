"""Short-term memory: per-session conversation history."""
from datetime import datetime


class ConversationStore:
    def __init__(self, db):
        self.db = db

    def add(self, session_id: str, role: str, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO conversation (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
                (session_id, role, content or "", datetime.now().isoformat()))

    def recent(self, session_id: str, limit: int):
        """The last `limit` messages, oldest first, in OpenAI message format."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit)).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def unsummarized_outside_window(self, session_id: str, keep: int):
        """Unsummarized messages older than the last `keep` messages: (id, role, content)."""
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT id, role, content FROM conversation "
                "WHERE session_id=? AND summarized=0 AND id NOT IN "
                "(SELECT id FROM conversation WHERE session_id=? ORDER BY id DESC LIMIT ?) "
                "ORDER BY id", (session_id, session_id, keep)).fetchall()

    def mark_summarized(self, ids) -> None:
        with self.db.connect() as conn:
            conn.executemany("UPDATE conversation SET summarized=1 WHERE id=?", [(i,) for i in ids])

    def clear(self, session_id: str) -> int:
        with self.db.connect() as conn:
            return conn.execute("DELETE FROM conversation WHERE session_id=?", (session_id,)).rowcount
