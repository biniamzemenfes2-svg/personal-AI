"""Central configuration. Every module reads settings from here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(os.environ.get("AETHER_HOME", "~/AetherOS")).expanduser()
WORKSPACE_DIR = ROOT_DIR / "workspace"
DB_PATH = ROOT_DIR / "system_v2.db"
LOG_PATH = ROOT_DIR / "aetheros.log"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None
MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Daemon thresholds
DAEMON_INTERVAL = 15
CPU_ALERT_PERCENT = 85.0
RAM_ALERT_PERCENT = 90.0
TASK_BACKLOG_ALERT = 5

# Memory / kernel
MEMORY_TOP_K = 3
MEMORY_MIN_SCORE = 0.35
MAX_TOOL_ROUNDS = 5


def ensure_dirs() -> None:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Agent engine
AGENT_MAX_STEPS = 6
AGENT_MAX_REPLANS = 2

# Web server (binds to localhost by default; set AETHER_API_TOKEN before exposing it)
API_HOST = os.environ.get("AETHER_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("AETHER_PORT", "8000"))
API_TOKEN = os.environ.get("AETHER_API_TOKEN") or None
