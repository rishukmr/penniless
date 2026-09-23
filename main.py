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
  [bold white]1.[/bold white]  [cyan]Complete Installation[/cyan]
     [dim]Set up everything: Python deps, wallet, Superteam,
     LLM providers, Claude Code skill, agent.mjs config[/dim]

  [bold white]2.[/bold white]  [green]Run the Software[/green]
     [dim]Start the AI agent — scan Superteam, IssueHunt, Algora
     and GitHub for bounties, propose a task, and implement it[/dim]

  [bold white]3.[/bold white]  [red]Exit[/red]
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
        if choice in ("1", "2", "3"):
            return choice
        console.print("  [dim]Please enter 1, 2, or 3[/dim]")


# ─── Option handlers ──────────────────────────────────────────────────────────

def _run_installation() -> None:
    from src.installer import run_installation
    run_installation()
    input("\n  Press Enter to return to the menu...")


def _run_software() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        console.print(Panel(
            "[bold red]❌  .env file not found.[/bold red]\n\n"
            "Please run [bold]Complete Installation[/bold] (option 1) first.",
            border_style="red",
        ))
        input("\n  Press Enter to return to the menu...")
        return

    # Reload config from the .env that's on disk right now
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
        return

    # Refresh the LLM client with current config
    from src.llm_client import llm
    llm._refresh()

    from src.agent_runner import run_agent
    try:
        run_agent()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        console.print("[dim]Check your .env and API keys, then try again.[/dim]")

    input("\n  Press Enter to return to the menu...")


# ─── Main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    while True:
        choice = _show_menu()

        if choice == "1":
            _run_installation()
        elif choice == "2":
            _run_software()
        elif choice == "3":
            console.print("\n  [dim]Goodbye.[/dim]\n")
            sys.exit(0)


if __name__ == "__main__":
    main()
