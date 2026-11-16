import json
import sqlite3
import unittest
from datetime import datetime
from unittest import mock

import config
from core.kernel import Kernel
from database import Database
from memory.consolidator import Consolidator
from memory.conversation import ConversationStore
from memory.vector_store import MSG_DUPLICATE, MSG_FAILED, MSG_STORED, VectorStore
from tests.helpers import FakeClient, RecordingClient, TempCase, make_msg, make_tool_call
from tools.file_manager import FileManager
from tools.task_manager import TaskManager

NOW = datetime(2026, 11, 13, 12, 0, 0)


class MigrationTests(TempCase):
    def test_legacy_database_is_upgraded(self):
        path = self.tmp / "legacy.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE vector_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "text TEXT NOT NULL, embedding TEXT NOT NULL, timestamp TEXT)")
        conn.execute("INSERT INTO vector_memory (text, embedding, timestamp) VALUES "
                     "('User asked: hi | OS responded: hello', '[1,0]', '2026-01-01T00:00:00')")
        conn.execute("INSERT INTO vector_memory (text, embedding, timestamp) VALUES "
                     "('Created file notes.txt', '[0,1]', '2026-01-01T00:00:00')")
        conn.commit()
        conn.close()

        db = Database(path)
        Database(path)  # a second start must be a no-op
        with db.connect() as c:
            rows = c.execute("SELECT text, kind, importance FROM vector_memory ORDER BY id").fetchall()
        self.assertEqual(rows[0][1:], ("chat", 0.2))
        self.assertEqual(rows[1][1:], ("event", 0.5))


class VectorStoreMemoryTests(TempCase):
    def setUp(self):
        super().setUp()
        self.vs = VectorStore(self.db, FakeClient(), "m", now=lambda: NOW)

    def insert(self, text, emb, ts, importance=0.5, kind="event"):
        with self.db.connect() as c:
            c.execute("INSERT INTO vector_memory (text, embedding, timestamp, importance, kind) "
                      "VALUES (?, ?, ?, ?, ?)", (text, json.dumps(emb), ts, importance, kind))

    def test_duplicate_is_merged_and_keeps_higher_importance(self):
        self.assertEqual(self.vs.store("I am learning Flask", importance=0.3), MSG_STORED)
        self.assertEqual(self.vs.store("I am learning Flask", importance=0.9), MSG_DUPLICATE)
        items = self.vs.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["importance"], 0.9)

    def test_same_text_different_kind_is_not_merged(self):
        self.vs.store("I am learning Flask", kind="fact")
        self.assertEqual(self.vs.store("I am learning Flask", kind="event"), MSG_STORED)
        self.assertEqual(len(self.vs.list()), 2)

    def test_empty_text_rejected(self):
        self.assertEqual(self.vs.store("   "), MSG_FAILED)

    def test_recency_breaks_ties(self):
        self.insert("old flask note", [1, 0, 0.01], "2026-01-01T00:00:00")
        self.insert("new flask note", [1, 0, 0.01], "2026-11-12T00:00:00")
        self.assertEqual(self.vs.search("flask", top_k=1), ["new flask note"])

    def test_importance_breaks_ties(self):
        self.insert("minor flask note", [1, 0, 0.01], "2026-11-12T00:00:00", importance=0.1)
        self.insert("key flask fact", [1, 0, 0.01], "2026-11-12T00:00:00", importance=0.9)
        self.assertEqual(self.vs.search("flask", top_k=1), ["key flask fact"])

    def test_relevance_gate_beats_importance(self):
        self.insert("unrelated but important", [0, 0, 1], "2026-11-12T00:00:00", importance=1.0)
        self.assertEqual(self.vs.search("flask"), [])

    def test_access_stats_updated(self):
        self.insert("flask note", [1, 0, 0.01], "2026-11-12T00:00:00")
        self.vs.search("flask")
        with self.db.connect() as c:
            count, last = c.execute("SELECT access_count, last_accessed FROM vector_memory").fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(last, NOW.isoformat())

    def test_dimension_mismatch_skipped(self):
        self.insert("stale model vector", [1, 0], "2026-11-12T00:00:00")
        self.assertEqual(self.vs.search("flask"), [])

    def test_unparseable_timestamp_gets_neutral_recency(self):
        self.insert("flask note", [1, 0, 0.01], "garbage")
        self.assertEqual(self.vs.search("flask"), ["flask note"])

    def test_list_and_delete(self):
        self.vs.store("I am learning Flask")
        mid = self.vs.list()[0]["id"]
        self.assertIn("forgotten", self.vs.delete(mid))
        with self.assertRaises(LookupError):
            self.vs.delete(mid)


class ConversationTests(TempCase):
    def setUp(self):
        super().setUp()
        self.conv = ConversationStore(self.db)

    def test_recent_window_order_and_isolation(self):
        for i in range(5):
            self.conv.add("a", "user", f"m{i}")
        self.conv.add("b", "user", "other")
        self.assertEqual([m["content"] for m in self.conv.recent("a", 3)], ["m2", "m3", "m4"])
        self.assertEqual(len(self.conv.recent("b", 10)), 1)

    def test_unsummarized_outside_window(self):
        for i in range(10):
            self.conv.add("a", "user", f"m{i}")
        old = self.conv.unsummarized_outside_window("a", 4)
        self.assertEqual([c for _, _, c in old], [f"m{i}" for i in range(6)])
        self.conv.mark_summarized([i for i, _, _ in old])
        self.assertEqual(self.conv.unsummarized_outside_window("a", 4), [])

    def test_clear(self):
        self.conv.add("a", "user", "x")
        self.assertEqual(self.conv.clear("a"), 1)
        self.assertEqual(self.conv.recent("a", 5), [])


@mock.patch.object(config, "HISTORY_MESSAGES", 2)
@mock.patch.object(config, "CONSOLIDATE_AFTER", 4)
class ConsolidatorTests(TempCase):
    def fill(self, client):
        self.conv = ConversationStore(self.db)
        self.vs = VectorStore(self.db, client, "m", now=lambda: NOW)
        for i in range(8):
            self.conv.add("s", "user" if i % 2 == 0 else "assistant", f"flask message {i}")
        return Consolidator(client, self.conv, self.vs)

    def test_summarizes_old_messages_once(self):
        cons = self.fill(FakeClient(chat_script=[make_msg("- user is learning Flask")]))
        self.assertEqual(cons.maybe_run("s"), "- user is learning Flask")
        mem = self.vs.list()
        self.assertEqual((mem[0]["kind"], mem[0]["importance"]), ("summary", 0.6))
        self.assertIsNone(cons.maybe_run("s"))       # nothing left to summarize
        self.assertEqual(len(self.conv.recent("s", 50)), 8)  # history itself is kept

    def test_below_threshold_does_nothing(self):
        cons = self.fill(FakeClient())
        self.conv.clear("s")
        self.conv.add("s", "user", "hi")
        self.assertIsNone(cons.maybe_run("s"))

    def test_failed_store_leaves_messages_unsummarized(self):
        class NoEmbeddings(FakeClient):
            def _embed(self, input, model):
                raise RuntimeError("down")
        cons = self.fill(NoEmbeddings(chat_script=[make_msg("- summary")]))
        self.assertIsNone(cons.maybe_run("s"))
        self.assertEqual(len(self.conv.unsummarized_outside_window("s", 2)), 6)


class KernelMemoryTests(TempCase):
    def build(self, client):
        self.vs = VectorStore(self.db, client, "m", now=lambda: NOW)
        self.conv = ConversationStore(self.db)
        return Kernel(client, self.vs, FileManager(self.tmp / "ws"), TaskManager(self.db), self.conv)

    def test_history_is_sent_and_sessions_are_isolated(self):
        client = RecordingClient(chat_script=[make_msg("Hi A"), make_msg("Hi B"), make_msg("Hi C")])
        k = self.build(client)
        k.run_command("first")
        k.run_command("second")
        msgs = client.seen[-1]
        self.assertEqual(msgs[1:], [{"role": "user", "content": "first"},
                                    {"role": "assistant", "content": "Hi A"},
                                    {"role": "user", "content": "second"}])
        k.run_command("elsewhere", session_id="other")
        self.assertEqual(len(client.seen[-1]), 2)  # system + user only

    def test_stateless_run_leaves_no_history(self):
        k = self.build(RecordingClient(chat_script=[make_msg("ok")]))
        k.run_command("agent step", session_id=None)
        self.assertEqual(self.conv.recent("default", 10), [])

    def test_chat_is_not_dumped_into_long_term_memory(self):
        k = self.build(RecordingClient(chat_script=[make_msg("ok")]))
        k.run_command("hello")
        self.assertEqual(self.vs.list(), [])

    def test_save_to_memory_tool_stores_high_importance_fact(self):
        call = make_msg(tool_calls=[make_tool_call("1", "save_to_memory",
                                                   json.dumps({"fact": "User is learning Flask"}))])
        k = self.build(FakeClient(chat_script=[call, make_msg("Saved.")]))
        k.run_command("remember that I'm learning Flask")
        m = self.vs.list()[0]
        self.assertEqual((m["kind"], m["importance"]), ("fact", 0.9))


if __name__ == "__main__":
    unittest.main()
