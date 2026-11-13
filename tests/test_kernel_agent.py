import json
import unittest

from agent.engine import AgentEngine
from core.kernel import Kernel
from memory.vector_store import VectorStore
from tests.helpers import FakeClient, TempCase, make_msg, make_tool_call
from tools.file_manager import FileManager
from tools.task_manager import TaskManager


class KernelAgentTests(TempCase):
    def build(self, client):
        self.tasks = TaskManager(self.db)
        return Kernel(client, VectorStore(self.db, client, "m"),
                      FileManager(self.tmp / "ws"), self.tasks)

    @staticmethod
    def call(call_id, name, **args):
        return make_msg(tool_calls=[make_tool_call(call_id, name, json.dumps(args))])

    def test_tool_call_loop_adds_task(self):
        client = FakeClient(chat_script=[
            self.call("1", "manage_tasks", action="add", task_desc="learn Flask"),
            make_msg("Added it."),
        ])
        kernel = self.build(client)
        self.assertEqual(kernel.run_command("add a task"), "Added it.")
        self.assertEqual(self.tasks.list(), ["#1 [Medium] learn Flask"])
        self.assertFalse(kernel.last_run_failed)

    def test_failed_tool_is_flagged(self):
        client = FakeClient(chat_script=[
            self.call("1", "file_manager", action="read", filename="missing.txt"),
            make_msg("Could not find it."),
        ])
        kernel = self.build(client)
        kernel.run_command("read missing.txt")
        self.assertTrue(kernel.last_run_failed)

    def test_traversal_through_kernel_is_blocked(self):
        client = FakeClient(chat_script=[
            self.call("1", "file_manager", action="write", filename="../x.txt", content="no"),
            make_msg("Refused."),
        ])
        kernel = self.build(client)
        kernel.run_command("write outside")
        self.assertTrue(kernel.last_run_failed)
        self.assertFalse((self.tmp / "x.txt").exists())

    def test_bad_tool_arguments_do_not_crash(self):
        client = FakeClient(chat_script=[
            make_msg(tool_calls=[make_tool_call("1", "manage_tasks", "{not json")]),
            make_msg("ok"),
        ])
        self.assertEqual(self.build(client).run_command("x"), "ok")

    def test_agent_replans_after_tool_failure(self):
        client = FakeClient(
            plan_script=[make_msg('{"steps": ["read missing.txt", "never runs"]}'),
                         make_msg('{"steps": ["add task fallback"]}')],
            chat_script=[
                self.call("1", "file_manager", action="read", filename="missing.txt"),
                make_msg("It's missing."),
                self.call("2", "manage_tasks", action="add", task_desc="fallback"),
                make_msg("Added fallback."),
                make_msg("Summary."),
            ])
        kernel = self.build(client)
        plans = []
        out = AgentEngine(client, kernel).run(
            "goal", on_plan=lambda s, revised=False: plans.append((revised, s)))
        self.assertEqual(out, "Summary.")
        self.assertEqual(plans[1], (True, ["add task fallback"]))
        self.assertEqual(self.tasks.list(), ["#1 [Medium] fallback"])

    def test_agent_approval_can_skip(self):
        client = FakeClient(plan_script=[make_msg('{"steps": ["step one"]}')],
                            chat_script=[make_msg("Summary.")])
        kernel = self.build(client)
        results = []
        AgentEngine(client, kernel).run(
            "g", approve=lambda i, t, s: False,
            on_step=lambda i, t, s, r: results.append(r))
        self.assertEqual(results, ["SKIPPED by user"])


if __name__ == "__main__":
    unittest.main()
