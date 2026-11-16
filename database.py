"""SQLite access: schema creation, migrations and safe connection handling."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = str(path)
        self._init_schema()

    @contextmanager
    def connect(self):
        """Yield a connection; commit on success, roll back on error, always close.
        A new connection per call keeps this safe across threads."""
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'Medium',
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    timestamp TEXT,
                    importance REAL DEFAULT 0.5,
                    kind TEXT DEFAULT 'event',
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ts TEXT,
                    summarized INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation(session_id, id)")
            self._migrate(conn)

    @staticmethod
    def _migrate(conn) -> None:
        """Upgrade databases created by earlier versions (vector_memory had 3 columns)."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(vector_memory)")}
        fresh_kind = "kind" not in cols
        for name, ddl in [("importance", "REAL DEFAULT 0.5"), ("kind", "TEXT DEFAULT 'event'"),
                          ("last_accessed", "TEXT"), ("access_count", "INTEGER DEFAULT 0")]:
            if name not in cols:
                conn.execute(f"ALTER TABLE vector_memory ADD COLUMN {name} {ddl}")
        if fresh_kind:
            # The old kernel logged every exchange as a memory; mark those as low-value chatter.
            conn.execute("UPDATE vector_memory SET kind='chat', importance=0.2 "
                         "WHERE text LIKE 'User asked:%'")
