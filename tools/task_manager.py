"""Task registry backed by SQLite."""
from datetime import datetime


class TaskManager:
    def __init__(self, db):
        self.db = db

    def add(self, desc: str, priority: str = "Medium") -> str:
        if not desc:
            raise ValueError("Task description is required.")
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (task, priority, created_at) VALUES (?, ?, ?)",
                (desc, priority, datetime.now().isoformat()),
            )
            task_id = cur.lastrowid
        return f"Task #{task_id} added: {desc}"

    def list(self):
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, task, priority FROM tasks WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [f"#{r[0]} [{r[2]}] {r[1]}" for r in rows]

    def complete(self, task_id: int) -> str:
        with self.db.connect() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='done' WHERE id=? AND status='pending'", (task_id,)
            )
        if not cur.rowcount:
            raise LookupError(f"No pending task #{task_id}.")
        return f"Task #{task_id} completed."

    def delete(self, task_id: int) -> str:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if not cur.rowcount:
            raise LookupError(f"No task #{task_id}.")
        return f"Task #{task_id} deleted."

    def pending_count(self) -> int:
        with self.db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
