import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import Database  # noqa: E402


def make_msg(content=None, tool_calls=None):
    return types.SimpleNamespace(content=content, tool_calls=tool_calls)


def make_tool_call(call_id, name, args_json):
    return types.SimpleNamespace(
        id=call_id, function=types.SimpleNamespace(name=name, arguments=args_json))


class FakeClient:
    """Scripted OpenAI stand-in. chat_script / plan_script are lists of messages returned in order.
    Embeddings are deterministic 3-d vectors based on keywords."""

    def __init__(self, chat_script=None, plan_script=None):
        self.chat_script = list(chat_script or [])
        self.plan_script = list(plan_script or [])
        self.chat = types.SimpleNamespace(completions=self)
        self.embeddings = types.SimpleNamespace(create=self._embed)

    def create(self, **kw):
        script = self.plan_script if kw.get("response_format") else self.chat_script
        msg = script.pop(0) if script else make_msg("done")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    def _embed(self, input, model):
        t = input[0].lower()
        vec = [float("flask" in t), float("python" in t), 0.01]
        return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=vec)])


class TempCase(unittest.TestCase):
    """Gives each test a temp dir (self.tmp) and a fresh Database (self.db)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.db = Database(self.tmp / "test.db")
