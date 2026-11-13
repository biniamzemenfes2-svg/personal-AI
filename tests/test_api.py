import json
import unittest
from types import SimpleNamespace

from agent.engine import AgentEngine
from api.server import create_app
from core.kernel import Kernel
from memory.vector_store import VectorStore
from tests.helpers import FakeClient, TempCase, make_msg, make_tool_call
from tools.file_manager import FileManager
from tools.task_manager import TaskManager


class StubDaemon:
    def get_alerts(self):
        return ["⚠️ test alert"]


class ApiTests(TempCase):
    def make(self, client=None, token=None):
        client = client or FakeClient()
        tasks = TaskManager(self.db)
        kernel = Kernel(client, VectorStore(self.db, client, "m"),
                        FileManager(self.tmp / "ws"), tasks)
        system = SimpleNamespace(kernel=kernel, agent=AgentEngine(client, kernel),
                                 tasks=tasks, files=None, daemon=StubDaemon())
        app = create_app(system, token=token)
        app.testing = True
        return app.test_client(), system

    def test_index_served(self):
        c, _ = self.make()
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"AetherOS", r.data)

    def test_status(self):
        c, _ = self.make()
        data = c.get("/api/status").get_json()
        self.assertIn("CPU", data["specs"])
        self.assertEqual(data["alerts"], ["⚠️ test alert"])
        self.assertEqual(data["tasks"], [])

    def test_chat_with_tool_call(self):
        client = FakeClient(chat_script=[
            make_msg(tool_calls=[make_tool_call("1", "manage_tasks",
                     json.dumps({"action": "add", "task_desc": "learn Flask"}))]),
            make_msg("Added."),
        ])
        c, system = self.make(client)
        r = c.post("/api/chat", json={"message": "add a task"})
        self.assertEqual(r.get_json(), {"reply": "Added.", "tool_failed": False})
        self.assertEqual(system.tasks.list(), ["#1 [Medium] learn Flask"])

    def test_validation(self):
        c, _ = self.make()
        self.assertEqual(c.post("/api/chat", json={}).status_code, 400)
        self.assertEqual(c.post("/api/chat", json={"message": "  "}).status_code, 400)
        self.assertEqual(c.post("/api/chat", data="nope").status_code, 400)
        self.assertEqual(c.post("/api/tasks", json={"task": "x", "priority": "Urgent"}).status_code, 400)
        self.assertEqual(c.post("/api/agent/run", json={"goal": "g"}).status_code, 400)

    def test_task_crud(self):
        c, _ = self.make()
        self.assertEqual(c.post("/api/tasks", json={"task": "a", "priority": "High"}).status_code, 201)
        self.assertEqual(c.get("/api/tasks").get_json()["tasks"], ["#1 [High] a"])
        self.assertEqual(c.post("/api/tasks/1/complete").status_code, 200)
        self.assertEqual(c.post("/api/tasks/1/complete").status_code, 404)
        self.assertEqual(c.delete("/api/tasks/1").status_code, 200)
        self.assertEqual(c.delete("/api/tasks/1").status_code, 404)

    def test_agent_plan_then_run_with_edited_steps(self):
        client = FakeClient(
            plan_script=[make_msg('{"steps": ["one", "two"]}')],
            chat_script=[make_msg("did edited"), make_msg("Summary.")])
        c, _ = self.make(client)
        plan = c.post("/api/agent/plan", json={"goal": "g"}).get_json()
        self.assertEqual(plan["steps"], ["one", "two"])
        out = c.post("/api/agent/run", json={"goal": "g", "steps": ["edited step"]}).get_json()
        self.assertEqual(out["summary"], "Summary.")
        self.assertEqual([s["step"] for s in out["steps"]], ["edited step"])
        self.assertTrue(out["steps"][0]["ok"])

    def test_token_required(self):
        c, _ = self.make(token="s3cret")
        self.assertEqual(c.get("/api/status").status_code, 401)
        self.assertEqual(c.get("/api/status", headers={"X-API-Token": "wrong"}).status_code, 401)
        self.assertEqual(c.get("/api/status", headers={"X-API-Token": "s3cret"}).status_code, 200)
        self.assertEqual(c.get("/api/status", headers={"Authorization": "Bearer s3cret"}).status_code, 200)
        self.assertEqual(c.get("/").status_code, 200)  # the page itself loads; its API calls need the token

    def test_internal_error_is_json(self):
        class Boom(FakeClient):
            def create(self, **kw):
                raise RuntimeError("api down")
        c, _ = self.make(Boom())
        r = c.post("/api/chat", json={"message": "hi"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("api down", r.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
