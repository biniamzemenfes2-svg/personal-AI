"""Builds the full AetherOS object graph. Shared by the terminal app and the web server."""
from dataclasses import dataclass

from openai import OpenAI

import config
from agent.engine import AgentEngine
from core.kernel import Kernel
from database import Database
from memory.vector_store import VectorStore
from memory.consolidator import Consolidator
from memory.conversation import ConversationStore
from monitoring.daemon import Daemon
from tools.file_manager import FileManager
from tools.task_manager import TaskManager


@dataclass
class System:
    kernel: Kernel
    agent: AgentEngine
    tasks: TaskManager
    files: FileManager
    daemon: Daemon
    memory: VectorStore
    conversation: ConversationStore


def api_key_missing() -> bool:
    return not config.OPENAI_API_KEY and not config.OPENAI_BASE_URL


def build_system(start_daemon: bool = True) -> System:
    config.ensure_dirs()
    client = OpenAI(api_key=config.OPENAI_API_KEY or "not-needed", base_url=config.OPENAI_BASE_URL)
    db = Database(config.DB_PATH)
    memory = VectorStore(db, client, config.EMBED_MODEL)
    files = FileManager(config.WORKSPACE_DIR)
    tasks = TaskManager(db)
    conversation = ConversationStore(db)
    kernel = Kernel(client, memory, files, tasks, conversation,
                    Consolidator(client, conversation, memory))
    daemon = Daemon(tasks)
    if start_daemon:
        daemon.start()
    return System(kernel, AgentEngine(client, kernel), tasks, files, daemon, memory, conversation)
