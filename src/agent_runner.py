"""
agent_runner.py — The core AI agent loop.

Flow:
  1.  Print status banner (wallet balances + active LLM providers)
  2.  Scan all platforms for earning opportunities
  3.  Load the safe-agent-commerce skill rules as system context
  4.  Ask LLM to analyse and recommend ONE task (with evidence)
  5.  Present proposal to user — human must type GO to proceed
  6.  On GO: LLM writes the actual code fix + PR instructions
  7.  Log outcome to ledger.md
"""
from __future__ import annotations

import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.config import cfg
from src.llm_client import llm
from src.bounty_scanner import scan_all
from src.wallet_monitor import get_status

console = Console()

# Paths
_PROJECT_ROOT = Path(__file__).parent.parent
_SKILL_PATH = _PROJECT_ROOT / ".claude" / "skills" / "safe-agent-commerce" / "SKILL.md"
_LEDGER_PATH = _PROJECT_ROOT / "ledger.md"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_skill_context() -> str:
    if _SKILL_PATH.exists():
        return _SKILL_PATH.read_text(encoding="utf-8")
    return (
        "SAFETY RULES (fallback — install skill for full rules):\n"
        "1. Payment evidence before work — verify the source has paid someone before.\n"
        "2. Human approves every PR, bid, and account creation.\n"
        "3. Never move private keys or seed phrases anywhere.\n"
        "4. Check KYC requirements BEFORE starting work.\n"
        "5. Log every outward artifact immediately.\n"
    )


def _build_system_prompt() -> str:
    skill = _load_skill_context()
    return f"""You are a careful, honest AI earning agent following these safety rules:

{skill}

────────────────────────────────────────────
Agent name : {cfg.AGENT_NAME}
Base wallet: {cfg.EVM_WALLET or "not set"}
Sol wallet : {cfg.SOL_WALLET or "not set"}
Budget     : $0 — never spend money to earn money
────────────────────────────────────────────

You find legitimate tasks where code contributions earn real money (USDC).
You NEVER start work without explicit human GO.
You NEVER create accounts without human consent.
You ALWAYS cite verifiable evidence of past payment.
"""


def _show_wallet_panel() -> None:
    status = get_status()
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    t.add_column("Chain", style="cyan", width=12)
    t.add_column("Balance", style="bold green", width=16)
    t.add_column("Address", style="dim")

    base = status["base_usdc"]
    sol  = status["sol_usdc"]

    t.add_row(
        "Base (EVM)",
        f"${base:.4f} USDC" if isinstance(base, float) else str(base),
        status["evm_wallet"],
    )
    t.add_row(
        "Solana",
        f"${sol:.4f} USDC"  if isinstance(sol,  float) else str(sol),
        status["sol_wallet"],
    )

    total = status["total_usd"]
    console.print(Panel(
        t,
        title=f"[bold green]💰 Wallet  |  Total: ${total:.4f} USDC[/bold green]",
        border_style="green",
    ))


def _show_opportunities_table(opps: list[dict]) -> None:
    if not opps:
        return
    t = Table(box=box.SIMPLE_HEAVY, show_lines=False)
    t.add_column("#",        width=3,  style="dim")
    t.add_column("Source",   width=11, style="cyan")
    t.add_column("Type",     width=9)
    t.add_column("Title",    width=38)
    t.add_column("Reward",   width=10, style="green")
    t.add_column("Verified", width=8)

    _TYPE_ICON = {"written": "✍️ text", "code": "💻 code", "video": "🎥 video", "other": "❓ other"}

    for i, o in enumerate(opps[:15], 1):
        reward = o.get("reward_usd")
        reward_str = f"${reward:.0f}" if isinstance(reward, (int, float)) else "?"
        verified = "✅" if o.get("paid_before") else "❓"
        title = (o.get("title") or o.get("slug") or "")[:36]
        ctype = _TYPE_ICON.get(o.get("content_type", ""), "")
        t.add_row(str(i), o.get("source", "?"), ctype, title, reward_str, verified)

    console.print(Panel(t, title="🔍 Open Opportunities", border_style="blue"))


def _append_ledger(entry: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not _LEDGER_PATH.exists():
        example_path = _PROJECT_ROOT / "ledger.example.md"
        if example_path.exists():
            _LEDGER_PATH.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            _LEDGER_PATH.write_text("# Penniless Agent Ledger\n\n| DATE | PLATFORM | TASK | PR_URL | Status |\n", encoding="utf-8")
    with open(_LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n<!-- {timestamp} -->\n{entry}\n")


def _is_content_task(proposal: str) -> bool:
    """Detect if the approved proposal is a written content task (not code)."""
    p = proposal.lower()
    content_signals = ["blog", "article", "post", "tweet", "thread", "write",
                       "content", "explainer", "feedback", "review", "guide",
                       "superteam", "social"]
    code_signals = ["diff", "```python", "```rust", "```typescript", "bug fix",
                    "github.com", "pull request", "fork", "clone", "commit"]
    content_score = sum(1 for k in content_signals if k in p)
    code_score    = sum(1 for k in code_signals if k in p)
    return content_score > code_score


def _execute_code_task(proposal: str) -> None:
    """Generate a full code solution + PR instructions for a code bounty."""
    console.print("\n[bold green]✅ GO received — generating code solution...[/bold green]\n")

    execute_prompt = f"""The human approved the task you proposed.

Now produce the full implementation:

## 1. Repository
State the exact GitHub repo URL and which file(s) to change.

## 2. Code Fix (diff format)
Show the exact change using unified diff or full file content.
Include only real, working code — no pseudocode.

## 3. PR Title
One-line title (imperative mood, <72 chars).

## 4. PR Description
- What problem does this fix?
- How does the fix work?
- How to test it?
(Disclose: "This PR was generated with AI assistance.")

## 5. Git Commands
```bash
# Exact shell commands to fork, clone, branch, commit, push, and open PR
```

## 6. Ledger Entry
One-line entry for ledger.md (format: `| DATE | PLATFORM | TASK | PR_URL | Status |`).

────────────────────────────────────────
Approved proposal (summary):
{proposal[:600]}
────────────────────────────────────────

Produce real, submission-ready output only."""

    response = llm.chat(
        messages=[{"role": "user", "content": execute_prompt}],
        system=_build_system_prompt(),
        max_tokens=4096,
    )

    console.print(Panel(Markdown(response), title="[bold green]🔧 Code Solution[/bold green]", border_style="green"))

    ledger_match = re.search(r"\|.*\|.*\|.*\|", response)
    if ledger_match:
        _append_ledger(ledger_match.group(0))
        console.print("[dim]✎ Ledger entry recorded.[/dim]")

    console.print("\n[bold]📋 Your next steps:[/bold]")
    console.print("  1. [yellow]Review every line of the solution above[/yellow] — you are responsible for what you submit")
    console.print("  2. Test it locally (run tests, lint, build)")
    console.print("  3. Run the git commands shown → submit PR")
    console.print(f"  4. Update [cyan]{_LEDGER_PATH}[/cyan] once the PR URL is live")
    console.print("\n[dim]Reminder: merged PR ≠ money received. Money = on-chain balance in wallet.[/dim]")


def _execute_content_task(proposal: str) -> None:
    """Generate actual written content for a Superteam content bounty."""
    console.print("\n[bold green]✅ GO received — writing content...[/bold green]\n")

    content_prompt = f"""The human approved the content bounty you proposed.

Now produce the COMPLETE submission-ready content. Be thorough and high quality.

## 1. Bounty Details
Restate: Platform, URL, Reward, Deadline.

## 2. Full Content (ready to copy-paste and submit)

Write the COMPLETE content piece right now. This must be:
- Fully written out (not a template or outline)
- High quality and engaging
- Tailored to the specific bounty requirements
- Between 300-1500 words depending on format (article = longer, social post = shorter)

Format as appropriate for the content type:
- Blog/Article: Full markdown with headings, paragraphs, conclusion
- Twitter/X Thread: Number each tweet (1/N), max 280 chars each
- Social Post: Ready to copy-paste caption + hashtags
- Feedback/Review: Structured points with specific details

## 3. Submission Instructions
Exact steps:
1. Go to [URL]
2. Click Submit
3. [Any specific fields to fill]
4. Paste the content above

## 4. Ledger Entry
`| DATE | superteam | TASK_TITLE | SUBMISSION_URL | Submitted |`

────────────────────────────────────────
Approved proposal:
{proposal[:600]}
────────────────────────────────────────

Write the FULL content now — do not abbreviate or use placeholders."""

    response = llm.chat(
        messages=[{"role": "user", "content": content_prompt}],
        system=_build_system_prompt(),
        max_tokens=4096,
    )

    console.print(Panel(Markdown(response), title="[bold green]✍️ Generated Content[/bold green]", border_style="green"))

    ledger_match = re.search(r"\|.*\|.*\|.*\|", response)
    if ledger_match:
        _append_ledger(ledger_match.group(0))
        console.print("[dim]✎ Ledger entry recorded.[/dim]")

    console.print("\n[bold]📋 Your next steps:[/bold]")
    console.print("  1. [yellow]Read the content above carefully[/yellow] — make sure it's accurate")
    console.print("  2. Go to the Superteam submission URL shown")
    console.print("  3. Copy-paste the content into the submission form")
    console.print("  4. Submit and note the submission URL for your ledger")
    console.print("\n[dim]Reminder: submission ≠ money received. Money = judges approve + on-chain payment.[/dim]")


def _execute_task(proposal: str) -> None:
    """Route to code or content executor based on proposal type."""
    if _is_content_task(proposal):
        _execute_content_task(proposal)
    else:
        _execute_code_task(proposal)


# ─── Phase 1: Find and propose a task ────────────────────────────────────────

def _propose_task(opps: list[dict]) -> Optional[str]:
    opps_json = json.dumps(opps[:15], indent=2, default=str)

    find_prompt = f"""Here are today's open earning opportunities:

{opps_json}

Pick ONE opportunity that best satisfies ALL of the following:
  a) The source has verified payment history (escrow confirmed or past paid submissions)
  b) The work is EITHER:
     - A written content piece (blog post, article, social media post, Twitter thread,
       explainer text, feedback, product review, or guide) — AI can fully produce this, OR
     - A code contribution (bug fix / feature / improvement)
     NOT video production, graphic design, audio, or physical work
  c) No KYC required to receive payment
  d) Achievable without spending any money
  e) Reward is USDC, SOL, USDG, or USD (not a project's own token)
  f) Deadline has not already passed

For your chosen task, respond with this exact structure:

### Chosen Task
**Platform:** <name>
**Task Type:** <"written content" OR "code contribution">
**URL:** <exact link>
**Reward:** <amount and token>
**Deadline:** <date or "open">

### Evidence of Payment
<concrete proof that Superteam has paid out before — they use escrow, so this is verified>

### Payout Requirements
<KYC? Minimum payout? Any submission conditions?>

### The Work
<For written content: What topic? What format? What length? What specific angle to cover?>
<For code: Which file? What bug or feature? Which repo?>

### Confidence
<Low / Medium / High> — <one sentence why>

---
Awaiting your GO to proceed. I will NOT start work until you say GO."""

    return llm.chat(
        messages=[{"role": "user", "content": find_prompt}],
        system=_build_system_prompt(),
        max_tokens=2048,
    )


# ─── Main entry point ─────────────────────────────────────────────────────────

def run_agent() -> None:
    # ── Header
    console.print(Panel.fit(
        f"[bold cyan]🤖 Penniless Agent — Active[/bold cyan]\n"
        f"Agent  : [yellow]{cfg.AGENT_NAME}[/yellow]\n"
        f"LLM    : [green]{llm.active_summary()}[/green]",
        border_style="cyan",
    ))

    # ── Wallet status
    console.print("\n[bold]📊 Wallet balances[/bold]")
    _show_wallet_panel()

    # ── Scan for opportunities
    console.print("\n[bold]🔍 Scanning platforms for opportunities...[/bold]")
    results = scan_all(verbose=True)
    all_opps = results.get("all", [])

    if not all_opps:
        console.print(Panel(
            "[yellow]No open listings found right now.[/yellow]\n\n"
            "• Superteam listings are time-limited — check back in 30 minutes\n"
            "• IssueHunt / Algora listings may be temporarily unavailable\n"
            "• Tip: run again later or check [link=https://superteam.fun/earn]superteam.fun/earn[/link]",
            title="No Opportunities",
            border_style="yellow",
        ))
        return

    console.print(f"\n  [bold green]{len(all_opps)}[/bold green] opportunities found across all platforms\n")
    _show_opportunities_table(all_opps)

    # ── LLM proposes best task
    console.print("\n[bold]🧠 Analysing opportunities with AI...[/bold]")
    proposal = _propose_task(all_opps)

    console.print(Panel(
        Markdown(proposal),
        title="[bold cyan]🤖 Agent Proposal[/bold cyan]",
        border_style="cyan",
    ))

    # ── Human approval gate
    console.print(
        "\n[bold yellow]⚡ Skill Rule #1: human approval required before any work.[/bold yellow]\n"
        "  [bold green]GO[/bold green]   — approve this task, generate the full solution\n"
        "  [bold blue]SKIP[/bold blue] — find a different task\n"
        "  [bold red]QUIT[/bold red] — return to main menu\n"
    )

    while True:
        choice = input("Your choice: ").strip().upper()
        if choice == "GO":
            _execute_task(proposal)
            break
        elif choice == "SKIP":
            console.print("[dim]Skipping. Re-running scan...[/dim]\n")
            run_agent()  # recurse once
            break
        elif choice == "QUIT":
            console.print("[dim]Returning to menu.[/dim]")
            break
        else:
            console.print("[dim]Type GO, SKIP, or QUIT[/dim]")
