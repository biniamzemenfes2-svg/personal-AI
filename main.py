"""AetherOS entry point."""
import logging
import sys

import config
import bootstrap
from interface import dashboard


def run_agent(console, agent, goal, auto):
    """Run the agent; /plan asks before each step, /auto runs without asking."""
    approve_all = auto

    def approve(i, total, step):
        nonlocal approve_all
        if approve_all:
            return True
        ans = console.input(f"[yellow]Run step {i}/{total}: {step}?[/yellow] [y/n/a(ll)] ").strip().lower()
        if ans in ("a", "all"):
            approve_all = True
            return True
        return ans in ("y", "yes")

    def on_plan(steps, revised=False):
        title = "Revised plan" if revised else "Plan"
        body = "\n".join(f"  {n}. {s}" for n, s in enumerate(steps, 1)) or "  (no remaining steps)"
        console.print(f"[bold]{title}:[/bold]\n{body}")

    def on_step(i, total, step, result):
        mark = "✘" if result.startswith(("FAILED", "SKIPPED")) else "✔"
        console.print(f"[dim]{mark} Step {i}/{total}: {step}[/dim]")

    console.print("[dim]Planning...[/dim]")
    response = agent.run(goal, on_plan=on_plan, on_step=on_step, approve=approve)
    return response


def main():
    config.ensure_dirs()
    logging.basicConfig(filename=config.LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    console = dashboard.console

    if bootstrap.api_key_missing():
        console.print("[bold red]OPENAI_API_KEY is missing. Copy .env.example to .env and set it.[/bold red]")
        sys.exit(1)

    system = bootstrap.build_system()
    kernel, agent, tasks, daemon = system.kernel, system.agent, system.tasks, system.daemon

    console.clear()
    dashboard.banner()
    try:
        while True:
            dashboard.render(daemon, tasks)
            user_input = console.input("\n[bold cyan]AetherOS[/bold cyan] λ ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "shutdown", "quit"):
                break
            try:
                if user_input.startswith(("/plan ", "/auto ")):
                    auto = user_input.startswith("/auto ")
                    goal = user_input[6:].strip()
                    response = run_agent(console, agent, goal, auto)
                else:
                    with console.status("[bold blue]Querying cognitive pipeline...", spinner="dots"):
                        response = kernel.run_command(user_input)
                dashboard.show_response(response)
            except Exception as e:
                logging.exception("Command failed")
                console.print(f"[bold red]Error:[/bold red] {e}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        console.print("[bold red]Deactivating kernel modules... Goodbye.[/bold red]")
        daemon.stop()


if __name__ == "__main__":
    main()
