"""AI orchestration: memory retrieval, tool schemas, multi-round tool calling."""
import json
import logging
from datetime import datetime

import config
from tools import hardware

log = logging.getLogger("aetheros.kernel")

TOOLS = [
    {"type": "function", "function": {
        "name": "get_hardware_specs",
        "description": "Retrieve current host hardware performance statistics.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "file_manager",
        "description": "Read, write or list files inside the AetherOS workspace.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["read", "write", "list"]},
            "filename": {"type": "string"},
            "content": {"type": "string"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "manage_tasks",
        "description": "Add, list, complete or delete items in the task registry.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["add", "list", "complete", "delete"]},
            "task_desc": {"type": "string"},
            "priority": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "task_id": {"type": "integer"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "save_to_memory",
        "description": "Explicitly save an important personal fact or user preference to long-term memory.",
        "parameters": {"type": "object", "properties": {"fact": {"type": "string"}},
                       "required": ["fact"]}}},
]


class Kernel:
    def __init__(self, client, memory, files, tasks):
        self.client = client
        self.memory = memory
        self.files = files
        self.tasks = tasks
        self._last_call_ok = True
        # True if the final tool call of the latest run_command failed (i.e. unrecovered)
        self.last_run_failed = False

    def _system_prompt(self, prompt: str) -> str:
        memories = self.memory.search(prompt, config.MEMORY_TOP_K, config.MEMORY_MIN_SCORE)
        context = "\n".join(f"- {m}" for m in memories) if memories else "No relevant past memories found."
        return (
            "You are AetherOS, a stateful, proactive AI Operating System.\n"
            f"Today's Date/Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Relevant context from your memory bank:\n{context}\n\n"
            "Respond with actionable answers. If a tool is needed, call it."
        )

    def _execute_tool(self, name: str, args: dict):
        """Run one tool. Failures are returned to the model as 'Error: ...' text and
        flagged in self._last_call_ok so callers (the agent) can detect them."""
        self._last_call_ok = True
        try:
            return self._dispatch(name, args)
        except Exception as e:
            log.warning("Tool %s failed: %s", name, e)
            self._last_call_ok = False
            return f"Error: {e}"

    def _dispatch(self, name: str, args: dict):
        if name == "get_hardware_specs":
            return hardware.get_specs()
        if name == "file_manager":
            action = args.get("action")
            if action == "write":
                result = self.files.write(args.get("filename", ""), args.get("content", ""))
                self.memory.store(f"Wrote file '{args.get('filename')}': {(args.get('content') or '')[:100]}")
                return result
            if action == "read":
                return self.files.read(args.get("filename", ""))
            if action == "list":
                return self.files.list()
            raise ValueError(f"Unknown file action: {action}")
        if name == "manage_tasks":
            action = args.get("action")
            if action == "add":
                result = self.tasks.add(args.get("task_desc"), args.get("priority", "Medium"))
                self.memory.store(f"User added a goal: {args.get('task_desc')}")
                return result
            if action == "list":
                return self.tasks.list()
            if action == "complete":
                return self.tasks.complete(int(args.get("task_id", -1)))
            if action == "delete":
                return self.tasks.delete(int(args.get("task_id", -1)))
            raise ValueError(f"Unknown task action: {action}")
        if name == "save_to_memory":
            return self.memory.store(args.get("fact", ""))
        raise ValueError(f"Unknown tool: {name}")

    def run_command(self, prompt: str) -> str:
        self.last_run_failed = False
        messages = [
            {"role": "system", "content": self._system_prompt(prompt)},
            {"role": "user", "content": prompt},
        ]
        output = ""
        for _ in range(config.MAX_TOOL_ROUNDS):
            resp = self.client.chat.completions.create(
                model=config.MODEL_NAME, messages=messages, tools=TOOLS)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                output = msg.content or ""
                break
            messages.append(msg)
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._execute_tool(call.function.name, args)
                self.last_run_failed = not self._last_call_ok
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": str(result)})
        else:
            # Tool budget exhausted: ask for a final answer without tools.
            resp = self.client.chat.completions.create(model=config.MODEL_NAME, messages=messages)
            output = resp.choices[0].message.content or ""

        self.memory.store(f"User asked: {prompt} | OS responded: {output[:150]}")
        return output
