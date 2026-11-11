import os
import sys
import json
import sqlite3
import subprocess
import psutil
import platform
import math
import threading
import time
from datetime import datetime
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from dotenv import load_dotenv

load_dotenv()

#config
API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = None  # Change to "http://localhost:11434/v1" if using local Ollama
MODEL_NAME = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"

console = Console()

class AetherOSKernel:
    def __init__(self):
        self.root_dir = os.path.expanduser("~/AetherOS")
        os.makedirs(self.root_dir, exist_ok=True)
        self.db_path = os.path.join(self.root_dir, "system_v2.db")
        self.daemon_alerts = []
        self.alert_lock = threading.Lock()
        
        # Test API Key Configuration
        if API_KEY == "your-api-key-here" and not BASE_URL:
            console.print("[bold red]WARNING: OpenAI API key is missing. Set the OPENAI_API_KEY environment variable.[/bold red]")
        
        try:
            self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        except Exception as e:
            console.print(f"[bold red]Initialization Error:[/bold red] Could not establish LLM client: {e}")
            sys.exit(1)

        self._init_db()
        self._start_background_daemon()

    def _init_db(self):
        """Builds a persistent relational database and vector-store register."""
        with sqlite3.connect(self.db_path) as conn:
            # Active tasks queue
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'Medium',
                    created_at TEXT
                )
            """)
            # Semantic Long Term Vector Memory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    timestamp TEXT
                )
            """)
            conn.commit()

    # VECTOR MEMORY ENGINE (RAG)
    def _cosine_similarity(self, vec1, vec2):
        dot_product = sum(x * y for x, y in zip(vec1, vec2))
        norm_a = math.sqrt(sum(x * x for x in vec1))
        norm_b = math.sqrt(sum(y * y for y in vec2))
        if not norm_a or not norm_b:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def get_embedding(self, text):
        """Generates a text vector embedding using OpenAI's API."""
        try:
            response = self.client.embeddings.create(
                input=[text],
                model=EMBED_MODEL
            )
            return response.data[0].embedding
        except Exception:
            return None

    def store_memory(self, text):
        """Encodes and saves an event or conversation into semantic memory."""
        embedding = self.get_embedding(text)
        if not embedding:
            return "Failed to process memory vector."
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO vector_memory (text, embedding, timestamp) VALUES (?, ?, ?)",
                (text, json.dumps(embedding), datetime.now().isoformat())
            )
            conn.commit()
        return "Memory permanently indexed."

    def retrieve_memories(self, query, top_k=3):
        """Performs a vector similarity search across past events."""
        query_vector = self.get_embedding(query)
        if not query_vector:
            return []

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT text, embedding FROM vector_memory").fetchall()

        scored_memories = []
        for text, emb_str in rows:
            emb = json.loads(emb_str)
            score = self._cosine_similarity(query_vector, emb)
            scored_memories.append((text, score))

        # Sort based on similarity confidence
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        return [text for text, score in scored_memories[:top_k] if score > 0.35]

    # PROACTIVE SYSTEM DAEMON (BACKGROUND THREAD)
    def _start_background_daemon(self):
        """Forks a background thread to act as a system supervisor."""
        daemon_thread = threading.Thread(target=self._daemon_loop, daemon=True)
        daemon_thread.start()

    def _daemon_loop(self):
        """Loops continuously every 15 seconds checking resource boundaries."""
        while True:
            alerts = []
            # 1. Inspect local machine health
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            if cpu > 85.0:
                alerts.append(f"⚠️ High CPU Load: {cpu}%")
            if ram > 90.0:
                alerts.append(f"⚠️ Memory Exhaustion Warning: {ram}% RAM in use")

            # 2. Inspect pending OS Tasks
            try:
                with sqlite3.connect(self.db_path) as conn:
                    backlog = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
                if backlog > 5:
                    alerts.append(f"📋 Task Backlog heavy: {backlog} items waiting execution")
            except Exception:
                pass

            with self.alert_lock:
                self.daemon_alerts = alerts

            time.sleep(15)

    #PHYSICAL ENVIRONMENT TOOLS
    def tool_get_hardware_specs(self):
        return f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}% | OS: {platform.system()}"

    def tool_file_manager(self, action, filename, content=None):
        path = os.path.join(self.root_dir, filename)
        if action == "write":
            with open(path, "w") as f:
                f.write(content)
            self.store_memory(f"Created/Overwrote local file '{filename}' containing: {content[:100]}")
            return f"Saved file to {filename}"
        elif action == "read":
            if not os.path.exists(path):
                return "Error: File does not exist."
            with open(path, "r") as f:
                return f.read()

    def tool_manage_tasks(self, action, task_desc=None, priority="Medium"):
        with sqlite3.connect(self.db_path) as conn:
            if action == "add":
                conn.execute(
                    "INSERT INTO tasks (task, priority, created_at) VALUES (?, ?, ?)",
                    (task_desc, priority, datetime.now().isoformat())
                )
                conn.commit()
                self.store_memory(f"User added a system goal: {task_desc} (Priority: {priority})")
                return f"Task Added: {task_desc}"
            elif action == "list":
                tasks = conn.execute("SELECT task, priority FROM tasks WHERE status='pending'").fetchall()
                return [f"[{t[1]}] {t[0]}" for t in tasks]

    # PIPELINE / ORCHESTRATION
    def run_command(self, prompt):
        # 1. Semantically retrieve long-term context
        memories = self.retrieve_memories(prompt)
        memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No relevant past memories found."

        # 2. Package context inside System Guidelines
        system_instructions = (
            f"You are AetherOS, a stateful, proactive AI Operating System.\n"
            f"Today's Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"You have access to a semantic memory bank. Here is relevant context retrieved from your memory bank:\n"
            f"{memory_context}\n\n"
            "Respond to the user with actionable answers. If a tool needs to run to satisfy the request, call it."
        )

        tools = [
            {"type": "function", "function": {"name": "get_hardware_specs", "description": "Retrieve current host hardware performance statistics."}},
            {"type": "function", "function": {"name": "file_manager", "description": "Read or write local files inside the OS directory.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write"]}, "filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["action", "filename"]}}},
            {"type": "function", "function": {"name": "manage_tasks", "description": "Add or review items in the system task registry.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["add", "list"]}, "task_desc": {"type": "string"}, "priority": {"type": "string"}}, "required": ["action"]}}},
            {"type": "function", "function": {"name": "save_to_memory", "description": "Explicitly save an important personal fact or user preference to long-term memory.", "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}}
        ]

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": prompt}
        ]

        response = self.client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=tools)
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tool in msg.tool_calls:
                func_name = tool.function.name
                args = json.loads(tool.function.arguments)

                if func_name == "get_hardware_specs":
                    result = self.tool_get_hardware_specs()
                elif func_name == "file_manager":
                    result = self.tool_file_manager(args.get("action"), args.get("filename"), args.get("content"))
                elif func_name == "manage_tasks":
                    result = self.tool_manage_tasks(args.get("action"), args.get("task_desc"), args.get("priority", "Medium"))
                elif func_name == "save_to_memory":
                    result = self.store_memory(args.get("fact"))
                else:
                    result = "Error: Invalid tool call"

                messages.append({"role": "tool", "tool_call_id": tool.id, "name": func_name, "content": str(result)})

            # Resolve loop with tool insights
            final_response = self.client.chat.completions.create(model=MODEL_NAME, messages=messages)
            output = final_response.choices[0].message.content
        else:
            output = msg.content

        # Automatically store query/response interactions as cold memory
        self.store_memory(f"User asked: {prompt} | OS responded: {output[:150]}")
        return output

#INTERFACE PRESENTATION
def render_dashboard(kernel):
    # Fetch active variables safely
    with kernel.alert_lock:
        alerts = list(kernel.daemon_alerts)
        
    specs = kernel.tool_get_hardware_specs()
    tasks = kernel.tool_manage_tasks("list")

    # Render panels
    alert_text = "\n".join(alerts) if alerts else "[green]✔ All Background Services Healthy[/green]"
    alert_panel = Panel(alert_text, title="🛡️ Daemon Alerts", border_style="yellow" if alerts else "green")
    
    specs_panel = Panel(f"[cyan]{specs}[/cyan]", title="⚙️ Host Performance", border_style="blue")
    
    task_text = "\n".join(tasks[:4]) if tasks else "[dim]No pending tasks in queue.[/dim]"
    task_panel = Panel(task_text, title="📋 Task Backlog", border_style="purple")

    console.print(Columns([specs_panel, alert_panel, task_panel], equal=True))

def start_os():
    kernel = AetherOSKernel()
    console.clear()
    
    banner = (
        "           AETHER OPERATING SYSTEM - VERSION 2.0 (STATEFUL)           \n"
        "              Memory Core: SQL-Vector | Daemon: Active               "
    )
    console.print(Panel(banner, border_style="bright_cyan"))

    while True:
        try:
            render_dashboard(kernel)
            user_input = console.input("\n[bold cyan]AetherOS[/bold cyan] λ ")
            
            if user_input.lower() in ["exit", "shutdown", "quit"]:
                console.print("[bold red]Deactivating kernel modules... Goodbye.[/bold red]")
                break

            with console.status("[bold blue]Querying cognitive pipeline...", spinner="dots"):
                response = kernel.run_command(user_input)
            
            console.print(Panel(response, title="AetherOS Response", border_style="green"))
            console.print("\n")
        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[bold red]Kernel Crash Panic:[/bold red] {e}")

if __name__ == "__main__":
    start_os()
