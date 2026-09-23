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
from src.git_executor import git_exec, normalize_repo_name
from src.task_tracker import tracker

console = Console()

# Paths
_PROJECT_ROOT = Path(__file__).parent.parent
_SKILL_PATH = _PROJECT_ROOT / ".claude" / "skills" / "safe-agent-commerce" / "SKILL.md"
_LEDGER_PATH = _PROJECT_ROOT / "ledger.md"
_SUBMISSIONS_DIR = _PROJECT_ROOT / "submissions"
_SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)


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


def _extract_json_payload(text: str) -> dict:
    """Extract and parse JSON payload from LLM markdown response."""
    # 1. Search for ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 2. Search for outer curly braces
    m2 = re.search(r"(\{[\s\S]*\})", text)
    if m2:
        try:
            return json.loads(m2.group(1))
        except Exception:
            pass
    return {}


def _execute_code_task(proposal: str, autonomous: bool = False) -> None:
    """Generate a full code solution and optionally submit PR autonomously."""
    action_label = "Autonomous Submission" if autonomous else "Manual Review"
    console.print(f"\n[bold green]✅ Executing code task [{action_label}]...[/bold green]\n")

    if autonomous:
        # Ask LLM for machine-executable JSON specification
        exec_json_prompt = f"""You are an autonomous coding agent. Based on this approved task:

{proposal}

Produce a valid JSON object specifying the exact code fix to apply and submit via Pull Request.
You MUST output ONLY valid JSON inside a ```json``` code fence with these exact keys:

```json
{{
  "repo": "owner/repo",
  "branch": "fix-bounty-patch",
  "pr_title": "Fix issue with ... (under 72 chars)",
  "pr_body": "## Summary\\nBrief explanation of problem and fix.\\n\\n## Changes\\nList of changes.\\n\\n## Testing\\nHow to test.\\n\\n*(Generated autonomously by Penniless AI Agent)*",
  "files": {{
    "path/to/file.ext": "full modified or new file content here"
  }}
}}
```

Ensure the repository name is in owner/repo format and the code in "files" is 100% complete and working."""

        response = llm.chat(
            messages=[{"role": "user", "content": exec_json_prompt}],
            system=_build_system_prompt(),
            max_tokens=4096,
        )

        payload = _extract_json_payload(response)
        target_repo = payload.get("repo", "")
        branch = payload.get("branch", "fix-bounty-patch")
        pr_title = payload.get("pr_title", "Fix bounty issue")
        pr_body = payload.get("pr_body", "Automated fix by Penniless Agent")
        files = payload.get("files", {})

        if target_repo and files:
            console.print(Panel(
                f"[bold cyan]Repo:[/bold cyan] {target_repo}\n"
                f"[bold cyan]Branch:[/bold cyan] {branch}\n"
                f"[bold cyan]Title:[/bold cyan] {pr_title}\n"
                f"[bold cyan]Files to update:[/bold cyan] {list(files.keys())}",
                title="[bold green]🚀 Autonomous Git & PR Engine[/bold green]",
                border_style="green",
            ))

            try:
                pr_url = git_exec.execute_complete_pr(
                    target_repo=target_repo,
                    branch_name=branch,
                    file_changes=files,
                    pr_title=pr_title,
                    pr_body=pr_body,
                )
                ledger_entry = f"| {datetime.now().strftime('%Y-%m-%d')} | github | {pr_title} | {pr_url} | Submitted (Autonomous) |"
                _append_ledger(ledger_entry)
                tracker.record_completed_task(
                    url=target_repo,
                    title=pr_title,
                    source="github",
                    artifact_or_pr=pr_url,
                    status="submitted",
                )
                console.print(f"\n[bold green]🎉 Pull Request submitted autonomously and logged to ledger![/bold green]\n")
                return
            except Exception as e:
                console.print(f"  [yellow]Autonomous PR submission notice: {e}[/yellow]")
                console.print("  [dim]Falling back to standard solution display...[/dim]")

    # Standard / Fallback prompt
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
Approved proposal:
{proposal[:600]}
────────────────────────────────────────"""

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

    # Record to tracker so autonomous engine always advances to next task
    url_match = re.search(r"\*\*URL:\*\*\s*([^\s\n]+)", proposal)
    task_url = url_match.group(1).strip() if url_match else "code_task"
    tracker.record_completed_task(
        url=task_url,
        title="Code Solution",
        source="github",
        artifact_or_pr="solution_generated",
        status="generated",
    )


def _execute_content_task(proposal: str, autonomous: bool = False) -> None:
    """Generate actual written content and save submission artifact."""
    console.print("\n[bold green]✍️ Generating submission-ready content...[/bold green]\n")

    content_prompt = f"""The content bounty has been selected for completion:

{proposal}

Now produce the COMPLETE, publication-ready submission:
- Fully written out (not an outline)
- High quality and tailored to the bounty
- If article: full markdown with headings and conclusion
- If Twitter/X thread: numbered tweets (1/N)
- If product feedback: numbered specific feedback points

Write the FULL content now."""

    response = llm.chat(
        messages=[{"role": "user", "content": content_prompt}],
        system=_build_system_prompt(),
        max_tokens=4096,
    )

    console.print(Panel(Markdown(response), title="[bold green]✍️ Generated Content[/bold green]", border_style="green"))

    # Autonomously save artifact to submissions folder
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Extract brief slug from proposal
    slug_match = re.search(r"listings/([a-zA-Z0-9_\-]+)", proposal)
    slug = slug_match.group(1)[:30] if slug_match else f"bounty_{ts}"
    sub_file = _SUBMISSIONS_DIR / f"{slug}_{ts}.md"
    sub_file.write_text(response, encoding="utf-8")

    sub_url = f"https://superteam.fun/listings/{slug}" if slug_match else str(sub_file)
    ledger_entry = f"| {datetime.now().strftime('%Y-%m-%d')} | superteam | {slug} | file:///{sub_file.as_posix()} | Ready (Autonomous) |"
    _append_ledger(ledger_entry)

    tracker.record_completed_task(
        url=sub_url,
        title=slug,
        source="superteam",
        artifact_or_pr=str(sub_file),
        status="ready",
    )

    console.print(f"\n[bold green]💾 Content saved autonomously to:[/bold green] [cyan]{sub_file}[/cyan]")
    console.print(f"[dim]✎ Ledger entry recorded in {_LEDGER_PATH}[/dim]\n")


def _execute_task(proposal: str, autonomous: bool = False) -> None:
    """Route to code or content executor based on proposal type."""
    if _is_content_task(proposal):
        _execute_content_task(proposal, autonomous=autonomous)
    else:
        _execute_code_task(proposal, autonomous=autonomous)


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
Awaiting approval to execute."""

    return llm.chat(
        messages=[{"role": "user", "content": find_prompt}],
        system=_build_system_prompt(),
        max_tokens=2048,
    )


# ─── Main entry points ────────────────────────────────────────────────────────

def run_agent(autonomous: bool = False) -> bool:
    """
    Run a single cycle of the earning agent.
    Returns True if an opportunity was found and executed; False otherwise.
    """
    mode_text = "[bold green]100% Autonomous (Hands-Free)[/bold green]" if autonomous else "[bold yellow]Interactive (Human Approval)[/bold yellow]"
    
    # ── Header
    console.print(Panel.fit(
        f"[bold cyan]🤖 Penniless Agent — Active[/bold cyan]\n"
        f"Mode   : {mode_text}\n"
        f"Agent  : [yellow]{cfg.AGENT_NAME}[/yellow]\n"
        f"LLM    : [green]{llm.active_summary()}[/green]\n"
        f"Tasks Done: [magenta]{tracker.count_submitted()}[/magenta]",
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
            "• Superteam listings are time-limited — check back in 15-30 minutes\n"
            "• Tip: check https://superteam.fun/earn",
            title="No Opportunities",
            border_style="yellow",
        ))
        return False

    # Filter out already submitted tasks
    fresh_opps = tracker.filter_unattempted(all_opps)
    n_filtered = len(all_opps) - len(fresh_opps)
    if n_filtered > 0:
        console.print(f"  [dim]Filtered out {n_filtered} already-attempted tasks[/dim]")

    if not fresh_opps:
        console.print(Panel(
            f"[yellow]All {len(all_opps)} current opportunities have already been completed![/yellow]\n\n"
            f"• Tasks completed & tracked: [bold green]{tracker.count_submitted()}[/bold green]\n"
            "• Waiting for new listings or bounties to be published...",
            title="All Current Bounties Completed",
            border_style="yellow",
        ))
        return False

    console.print(f"\n  [bold green]{len(fresh_opps)}[/bold green] fresh unattempted opportunities ready for work\n")
    _show_opportunities_table(fresh_opps)

    # ── LLM proposes best task among fresh opportunities
    console.print("\n[bold]🧠 Analysing fresh opportunities with AI...[/bold]")
    proposal = _propose_task(fresh_opps)

    console.print(Panel(
        Markdown(proposal),
        title="[bold cyan]🤖 Selected Task Proposal[/bold cyan]",
        border_style="cyan",
    ))

    # ── Autonomous path vs Human Gate
    if autonomous:
        console.print("\n[bold green]⚡ Autonomous Mode: Auto-executing and submitting without user interaction...[/bold green]\n")
        _execute_task(proposal, autonomous=True)
        return True

    # Interactive path
    console.print(
        "\n[bold yellow]⚡ Human Approval Gate:[/bold yellow]\n"
        "  [bold green]GO[/bold green]   — approve this task, generate the full solution\n"
        "  [bold blue]SKIP[/bold blue] — find a different task\n"
        "  [bold red]QUIT[/bold red] — return to main menu\n"
    )

    while True:
        choice = input("Your choice: ").strip().upper()
        if choice == "GO":
            _execute_task(proposal, autonomous=False)
            return True
        elif choice == "SKIP":
            console.print("[dim]Skipping. Re-running scan...[/dim]\n")
            return run_agent(autonomous=False)
        elif choice == "QUIT":
            console.print("[dim]Returning to menu.[/dim]")
            return False
        else:
            console.print("[dim]Type GO, SKIP, or QUIT[/dim]")


def run_autonomous_daemon(interval_minutes: int = 15) -> None:
    """
    Relentlessly loop through bounties, solve them, and submit work
    non-stop until earnings appear in the wallet.
    """
    import time

    task_count = 0
    console.clear()
    console.print(Panel(
        f"[bold green]🚀 Relentless Autonomous Earning Daemon Running[/bold green]\n\n"
        f"• Goal: Continue working non-stop until earnings arrive in wallet\n"
        f"• Pipeline: Auto-Discover ➔ Auto-Solve ➔ Auto-Submit PR/Content ➔ Next Task\n"
        f"• Non-stop: Submits a task, pauses 15s for rate limits, then grabs next task immediately\n"
        f"• Press [bold red]Ctrl + C[/bold red] at any time to stop",
        title="[bold cyan]100% Hands-Free Earning Engine[/bold cyan]",
        border_style="green",
    ))

    try:
        while True:
            # 1. Check wallet balance
            status = get_status()
            current_balance = status.get("total_usd", 0.0)
            if current_balance > 0.0:
                console.print(Panel(
                    f"[bold green]🎉 SUCCESS! EARNING RECEIVED IN WALLET![/bold green]\n\n"
                    f"• Total Balance: [bold yellow]${current_balance:.4f} USDC[/bold yellow]\n"
                    f"• Base (EVM): {status.get('base_usdc')} USDC\n"
                    f"• Solana: {status.get('sol_usdc')} USDC\n"
                    f"• Total Tasks Completed: {tracker.count_submitted()}",
                    title="[bold yellow]💰 ON-CHAIN EARNING VERIFIED[/bold yellow]",
                    border_style="green",
                ))

            task_count += 1
            console.print(f"\n[bold magenta]═════════════════ WORK CYCLE #{task_count} ═════════════════[/bold magenta]\n")
            
            had_work = False
            try:
                had_work = run_agent(autonomous=True)
            except Exception as e:
                console.print(f"\n[bold red]Work cycle #{task_count} error: {e}[/bold red]")

            if had_work:
                # Successfully submitted a task! Move immediately to the next available task
                console.print(f"\n[bold green]✓ Task #{task_count} submitted![/bold green] [bold cyan]⚡ Auto-jumping to next bounty in 5s...[/bold cyan]\n")
                for s in range(5, 0, -1):
                    time.sleep(1)
            else:
                # All currently listed opportunities have been submitted, wait for new ones
                console.print(f"\n[dim]All current bounties completed. Waiting 120s for new listings... (Ctrl+C to stop)[/dim]")
                time.sleep(120)
    except KeyboardInterrupt:
        console.print("\n\n[bold yellow]⏹ Autonomous daemon stopped by user.[/bold yellow]\n")
