"""Rich terminal dashboard."""
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel

from tools import hardware

console = Console()


def banner():
    text = (
        "           AETHER OPERATING SYSTEM - VERSION 2.1 (MODULAR)           \n"
        "              Memory Core: SQL-Vector | Daemon: Active               "
    )
    console.print(Panel(text, border_style="bright_cyan"))


def render(daemon, tasks):
    alerts = daemon.get_alerts()
    pending = tasks.list()
    alert_text = "\n".join(alerts) if alerts else "[green]✔ All Background Services Healthy[/green]"
    task_text = "\n".join(pending[:4]) if pending else "[dim]No pending tasks in queue.[/dim]"
    console.print(Columns([
        Panel(f"[cyan]{hardware.get_specs()}[/cyan]", title="⚙️ Host Performance", border_style="blue"),
        Panel(alert_text, title="🛡️ Daemon Alerts", border_style="yellow" if alerts else "green"),
        Panel(task_text, title="📋 Task Backlog", border_style="purple"),
    ], equal=True))


def show_response(text):
    console.print(Panel(text, title="AetherOS Response", border_style="green"))
    console.print()
