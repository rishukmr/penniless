"""
main.py — Penniless AI Agent · Entry Point

Run this file to get started:
    python main.py

Options:
  1. Complete Installation  — set up everything from scratch (or re-run to update)
  2. Run the Software       — start the AI agent (scan → propose → approve → implement)
  3. Exit
"""
from __future__ import annotations

import sys
import os

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from pathlib import Path

# Make src/ importable from the project root
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

console = Console()

# ─── ASCII Banner ─────────────────────────────────────────────────────────────

_BANNER = r"""
 ____  _____ _   _ _   _ ___ _     _____ ____ ____
|  _ \| ____| \ | | \ | |_ _| |   | ____/ ___/ ___|
| |_) |  _| |  \| |  \| || || |   |  _| \___ \___ \
|  __/| |___| |\  | |\  || || |___| |___ ___) |__) |
|_|   |_____|_| \_|_| \_|___|_____|_____|____/____/

          AI AGENT  ·  v1.0  ·  $0 Start
    Real Paid Work  ·  USDC to Your Wallet  ·  24/7
"""

_MENU = """
  [bold white]1.[/bold white]  [cyan]Complete Installation / Re-configure[/cyan]
     [dim]Verify prerequisites, wallets, LLMs, and API connections[/dim]

  [bold white]2.[/bold white]  [bold green]Run Autonomous Agent (100% Hands-Free Loop)[/bold green]
     [dim]Continuous autonomous loop: auto-scans, auto-selects, auto-fixes,
     auto-submits PR via GitHub CLI, auto-saves content, and auto-logs to ledger[/dim]

  [bold white]3.[/bold white]  [green]Run Single Cycle (Autonomous)[/green]
     [dim]One-shot hands-free run: discovers, executes, and submits without asking[/dim]

  [bold white]4.[/bold white]  [yellow]Run Interactive Mode (With Approval Gate)[/yellow]
     [dim]Step-by-step mode requiring manual 'GO' confirmation before execution[/dim]

  [bold white]5.[/bold white]  [red]Exit[/red]
"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _env_status() -> str:
    """Return a one-line status string from .env."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return "[red]⚠  .env not found — run Complete Installation first[/red]"

    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

    llm_keys = ["NVIDIA_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY"]
    n_llm = sum(bool(env.get(k)) for k in llm_keys)
    agent = env.get("AGENT_NAME", "?")
    wallet = env.get("EVM_WALLET", "")
    wallet_short = wallet[:8] + "..." if wallet else "not set"

    status_parts = [
        f"agent=[yellow]{agent}[/yellow]",
        f"wallet=[green]{wallet_short}[/green]",
        f"llm=[cyan]{n_llm}/5[/cyan]",
        "[green]superteam=✅[/green]" if env.get("SUPERTEAM_API_KEY") else "[yellow]superteam=⚠[/yellow]",
    ]
    return "  " + "  ·  ".join(status_parts)


def _show_menu() -> str:
    console.clear()
    console.print(f"[bold magenta]{_BANNER}[/bold magenta]")
    console.print(Panel(
        _MENU,
        title="[bold yellow]Select an option[/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print(_env_status())
    console.print()

    while True:
        choice = input("  > ").strip()
        if choice in ("1", "2", "3", "4", "5"):
            return choice
        console.print("  [dim]Please enter 1, 2, 3, 4, or 5[/dim]")


# ─── Option handlers ──────────────────────────────────────────────────────────

def _run_installation() -> None:
    from src.installer import run_installation
    run_installation()
    input("\n  Press Enter to return to the menu...")


def _bootstrap_environment() -> bool:
    """Validate environment and initialize LLM client."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        console.print(Panel(
            "[bold red]❌  .env file not found.[/bold red]\n\n"
            "Please run [bold]Complete Installation[/bold] (option 1) first.",
            border_style="red",
        ))
        input("\n  Press Enter to return to the menu...")
        return False

    from src.config import cfg
    cfg.reload()

    issues = cfg.validate()
    if issues:
        console.print(Panel(
            "\n".join(f"[red]❌[/red] {i}" for i in issues) +
            "\n\n[dim]Fix these in .env, then run Complete Installation again.[/dim]",
            title="Configuration Issues",
            border_style="red",
        ))
        input("\n  Press Enter to return to the menu...")
        return False

    from src.llm_client import llm
    llm._refresh()
    return True


def _run_autonomous_loop() -> None:
    if not _bootstrap_environment():
        return
    from src.agent_runner import run_autonomous_daemon
    run_autonomous_daemon(interval_minutes=15)


def _run_single_autonomous() -> None:
    if not _bootstrap_environment():
        return
    from src.agent_runner import run_agent
    try:
        run_agent(autonomous=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")


def _run_interactive() -> None:
    if not _bootstrap_environment():
        return
    from src.agent_runner import run_agent
    try:
        run_agent(autonomous=False)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")

    input("\n  Press Enter to return to the menu...")


# ─── Main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    # Support direct CLI invocation for autonomous run
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--auto", "--daemon", "-a"):
            _run_autonomous_loop()
            return
        elif arg in ("--once", "-1"):
            _run_single_autonomous()
            return

    while True:
        choice = _show_menu()

        if choice == "1":
            _run_installation()
        elif choice == "2":
            _run_autonomous_loop()
        elif choice == "3":
            _run_single_autonomous()
        elif choice == "4":
            _run_interactive()
        elif choice == "5":
            console.print("\n  [dim]Goodbye.[/dim]\n")
            sys.exit(0)


if __name__ == "__main__":
    main()

