"""
installer.py — Complete installation wizard for the Penniless AI Agent.

Steps:
  1. Verify prerequisites (Python 3.8+, Node 20+, Git)
  2. Collect user inputs (agent name, wallet address)
  3. Install Python dependencies
  4. Register on Superteam (if not already done)
  5. Write/update the .env file
  6. Install the Claude Code skill (safe-agent-commerce)
  7. Configure agent.mjs with the user's wallet addresses
  8. Test LLM providers
  9. Print summary and remaining manual steps
"""
from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

_PROJECT_ROOT = Path(__file__).parent.parent
_SCRATCH_DIR  = Path.home() / ".gemini" / "antigravity" / "scratch"
_SKILL_SRC    = _SCRATCH_DIR / "the-penniless-agent" / "skills" / "safe-agent-commerce"
_SKILL_DST    = _PROJECT_ROOT / ".claude" / "skills" / "safe-agent-commerce"
_AGENT_MJS    = _SCRATCH_DIR / "echo-earning-agent" / "agent.mjs"
_ENV_FILE     = _PROJECT_ROOT / ".env"
_REQ_FILE     = _PROJECT_ROOT / "requirements.txt"


# ─── Utilities ────────────────────────────────────────────────────────────────

def _ok(label: str, detail: str = "") -> None:
    console.print(f"  [bold green]✅[/bold green] {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))

def _warn(label: str, detail: str = "") -> None:
    console.print(f"  [bold yellow]⚠ [/bold yellow] {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))

def _fail(label: str, detail: str = "") -> None:
    console.print(f"  [bold red]❌[/bold red] {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"  {prompt}{suffix}: ").strip()
    return value or default

def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def _read_env() -> dict[str, str]:
    """Read existing .env into a dict (ignoring comments)."""
    env: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def _write_env(values: dict[str, str]) -> None:
    """Write a clean .env file from a dict."""
    lines = [
        "# =============================================================",
        "# PENNILESS AI AGENT — ENVIRONMENT CONFIGURATION",
        "# Generated/updated by installer.py — never commit this file.",
        "# =============================================================",
        "",
        "# ── LLM PROVIDERS (Fallback order: NVIDIA → Gemini → Groq → OpenAI → Perplexity)",
        "# At least one must be set. Providers without a key are skipped automatically.",
        f"NVIDIA_API_KEY={values.get('NVIDIA_API_KEY', '')}",
        f"GEMINI_API_KEY={values.get('GEMINI_API_KEY', '')}",
        f"GEMINI_MODEL={values.get('GEMINI_MODEL', 'gemini-3.8-flash')}",
        f"GEMINI_REASONING_EFFORT={values.get('GEMINI_REASONING_EFFORT', 'medium')}",
        f"GROQ_API_KEY={values.get('GROQ_API_KEY', '')}",
        f"OPENAI_API_KEY={values.get('OPENAI_API_KEY', '')}",
        f"PERPLEXITY_API_KEY={values.get('PERPLEXITY_API_KEY', '')}",
        "",
        "# ── AGENT IDENTITY",
        f"AGENT_NAME={values.get('AGENT_NAME', 'my-earn-agent')}",
        f"AGENT_USERNAME={values.get('AGENT_USERNAME', '')}",
        "",
        "# ── SUPERTEAM (bounty listings + winnings claim)",
        f"SUPERTEAM_API_KEY={values.get('SUPERTEAM_API_KEY', '')}",
        f"SUPERTEAM_CLAIM_CODE={values.get('SUPERTEAM_CLAIM_CODE', '')}",
        f"SUPERTEAM_CLAIM_URL={values.get('SUPERTEAM_CLAIM_URL', '')}",
        "",
        "# ── WALLETS (receive-only PUBLIC addresses — NEVER paste private keys here)",
        f"EVM_WALLET={values.get('EVM_WALLET', '')}",
        f"SOL_WALLET={values.get('SOL_WALLET', '')}",
        "",
        "# ── GITHUB (optional — enables automatic PR creation)",
        "# Create token at: https://github.com/settings/tokens  (scope: repo)",
        f"GITHUB_TOKEN={values.get('GITHUB_TOKEN', '')}",
        f"GITHUB_USERNAME={values.get('GITHUB_USERNAME', '')}",
    ]
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── Steps ────────────────────────────────────────────────────────────────────

def _step_prerequisites() -> bool:
    console.print("\n[bold]Step 1 / 9 — Checking prerequisites[/bold]")

    python_ok = sys.version_info >= (3, 8)
    _ok("Python 3.8+", sys.version.split()[0]) if python_ok else _fail("Python 3.8+ required", sys.version.split()[0])

    node_path = shutil.which("node")
    if node_path:
        ver = _run(["node", "--version"]).stdout.strip()
        node_ok = True
        _ok("Node.js", ver)
    else:
        node_ok = False
        _fail("Node.js not found", "Install from nodejs.org (v20+)")

    git_path = shutil.which("git")
    if git_path:
        ver = _run(["git", "--version"]).stdout.strip()
        _ok("Git", ver)
        git_ok = True
    else:
        git_ok = False
        _fail("Git not found", "Install from git-scm.com")

    if not (python_ok and node_ok and git_ok):
        console.print("\n[bold red]Install missing prerequisites and run again.[/bold red]")
        return False
    return True


def _step_collect_inputs(env: dict[str, str]) -> dict[str, str]:
    console.print("\n[bold]Step 2 / 9 — Configuration[/bold]")

    # Agent name
    existing_name = env.get("AGENT_NAME", "")
    if existing_name:
        console.print(f"  Agent name : [green]{existing_name}[/green]  (from .env)")
        agent_name = existing_name
    else:
        agent_name = _ask("Agent name (e.g. your-name-agent)", "my-earn-agent")

    # EVM wallet
    existing_evm = env.get("EVM_WALLET", "")
    if existing_evm:
        console.print(f"  Base wallet: [green]{existing_evm}[/green]  (from .env)")
        evm_wallet = existing_evm
    else:
        console.print("  [dim]You need a Base (EVM) receive-only wallet address.[/dim]")
        console.print("  [dim]Create one free at metamask.io → copy the 0x... public address.[/dim]")
        evm_wallet = _ask("Base wallet address (0x...)")

    # Solana wallet (optional)
    existing_sol = env.get("SOL_WALLET", "")
    if existing_sol:
        console.print(f"  Sol wallet : [green]{existing_sol}[/green]  (from .env)")
        sol_wallet = existing_sol
    else:
        sol_wallet = _ask("Solana wallet (optional — press Enter to skip)", "")

    env["AGENT_NAME"] = agent_name
    env["EVM_WALLET"]  = evm_wallet
    env["SOL_WALLET"]  = sol_wallet
    return env


def _step_install_deps() -> bool:
    console.print("\n[bold]Step 3 / 9 — Installing Python dependencies[/bold]")
    if not _REQ_FILE.exists():
        _warn("requirements.txt not found — skipping")
        return True

    result = _run([sys.executable, "-m", "pip", "install", "-r", str(_REQ_FILE), "-q"])
    if result.returncode == 0:
        _ok("openai, python-dotenv, requests, rich — installed")
        return True
    else:
        _fail("pip install failed", result.stderr[:200])
        return False


def _step_register_superteam(env: dict[str, str]) -> dict[str, str]:
    console.print("\n[bold]Step 4 / 9 — Superteam registration[/bold]")

    if env.get("SUPERTEAM_API_KEY"):
        _ok("Already registered", f"username: {env.get('AGENT_USERNAME', '?')}")
        return env

    agent_name = env.get("AGENT_NAME", "my-earn-agent")
    console.print(f"  Registering [cyan]{agent_name}[/cyan] on Superteam...")

    try:
        r = requests.post(
            "https://superteam.fun/api/agents",
            json={"name": agent_name},
            timeout=12,
        )
        if r.ok:
            data = r.json()
            env["SUPERTEAM_API_KEY"]   = data.get("apiKey", "")
            env["SUPERTEAM_CLAIM_CODE"] = data.get("claimCode", "")
            env["AGENT_USERNAME"]       = data.get("username", "")
            claim_code = env["SUPERTEAM_CLAIM_CODE"]
            env["SUPERTEAM_CLAIM_URL"]  = f"https://superteam.fun/earn/claim/{claim_code}"
            _ok("Registered", f"username: {env['AGENT_USERNAME']}")
            if claim_code:
                console.print(f"\n  [bold yellow]⚠  SAVE YOUR CLAIM CODE: {claim_code}[/bold yellow]")
                console.print(f"  [dim]Claim URL: {env['SUPERTEAM_CLAIM_URL']}[/dim]\n")
        else:
            body = r.text[:120]
            _warn(f"Registration failed (HTTP {r.status_code}): {body}")
            console.print("  [dim]Name may already be taken. Try a different name or add key manually.[/dim]")
    except Exception as e:
        _warn(f"Superteam unreachable: {e}")
        console.print("  [dim]You can add SUPERTEAM_API_KEY manually to .env later.[/dim]")

    return env


def _step_write_env(env: dict[str, str]) -> None:
    console.print("\n[bold]Step 5 / 9 — Writing .env file[/bold]")
    _write_env(env)
    _ok(".env written", str(_ENV_FILE))


def _step_install_skill() -> None:
    console.print("\n[bold]Step 6 / 9 — Installing Claude Code skill[/bold]")

    if (_SKILL_DST / "SKILL.md").exists():
        _ok("safe-agent-commerce skill already installed")
        return

    if _SKILL_SRC.exists():
        _SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(_SKILL_SRC), str(_SKILL_DST), dirs_exist_ok=True)
        _ok("Skill installed", str(_SKILL_DST))
    else:
        console.print("  [dim]Skill source not found locally — cloning repo...[/dim]")
        clone_dir = _SCRATCH_DIR / "the-penniless-agent"
        if not clone_dir.exists():
            res = _run(["git", "clone",
                        "https://github.com/Echolonius/the-penniless-agent",
                        str(clone_dir)])
            if res.returncode != 0:
                _fail("Could not clone penniless-agent repo", res.stderr[:120])
                return
        _SKILL_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(_SKILL_SRC), str(_SKILL_DST), dirs_exist_ok=True)
        _ok("Skill installed", str(_SKILL_DST))


def _step_configure_agent_mjs(env: dict[str, str]) -> None:
    console.print("\n[bold]Step 7 / 9 — Configuring agent.mjs wallet addresses[/bold]")

    if not _AGENT_MJS.exists():
        # Try to clone it
        echo_dir = _SCRATCH_DIR / "echo-earning-agent"
        if not echo_dir.exists():
            console.print("  [dim]Cloning echo-earning-agent...[/dim]")
            _run(["git", "clone",
                  "https://github.com/Echolonius/echo-earning-agent",
                  str(echo_dir)])
        if not _AGENT_MJS.exists():
            _warn("agent.mjs not found — skipping wallet config for watcher")
            return

    content = _AGENT_MJS.read_text(encoding="utf-8")

    evm = env.get("EVM_WALLET", "")
    sol = env.get("SOL_WALLET", "")

    if evm:
        content = re.sub(
            r"const EVM_WALLET = '0x[a-fA-F0-9]+'",
            f"const EVM_WALLET = '{evm}'",
            content,
        )
    if sol:
        content = re.sub(
            r"const SOL_WALLET = '[A-Za-z0-9]+'",
            f"const SOL_WALLET = '{sol}'",
            content,
        )

    _AGENT_MJS.write_text(content, encoding="utf-8")
    _ok("agent.mjs wallet addresses set")


def _step_test_llm(env: dict[str, str]) -> None:
    console.print("\n[bold]Step 8 / 9 — Testing LLM providers[/bold]")

    # Reload config so it picks up freshly written .env
    from src.config import cfg
    cfg.reload()

    gemini_model = env.get("GEMINI_MODEL", "gemini-3.8-flash")
    providers_to_test = [
        ("NVIDIA",      env.get("NVIDIA_API_KEY", ""),      "https://integrate.api.nvidia.com/v1",                      "deepseek-ai/deepseek-v4.1-flash"),
        ("Gemini",      env.get("GEMINI_API_KEY", ""),      "https://generativelanguage.googleapis.com/v1beta/openai/",  gemini_model),
        ("Groq",        env.get("GROQ_API_KEY", ""),        "https://api.groq.com/openai/v1",                           "openai/gpt-oss-20b"),
        ("OpenAI",      env.get("OPENAI_API_KEY", ""),      "https://api.openai.com/v1",                                "gpt-4o-mini"),
        ("Perplexity",  env.get("PERPLEXITY_API_KEY", ""),  "https://api.perplexity.ai",                                "llama-3.1-sonar-large-128k-online"),
    ]

    import openai as _openai

    for name, key, base_url, model in providers_to_test:
        if not key:
            console.print(f"  [dim]- {name}: no key (skipped)[/dim]")
            continue
        try:
            client = _openai.OpenAI(api_key=key, base_url=base_url, timeout=30)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly one word: READY"}],
                max_tokens=200,
                temperature=0.5,
            )
            reply = (resp.choices[0].message.content or "").strip()
            if reply:
                _ok(f"{name}", f"{model} -> \"{reply[:40]}\"")
            else:
                _warn(f"{name}", "connected but got empty response")
        except Exception as e:
            _warn(f"{name}", f"{type(e).__name__}: {str(e)[:80]}")


def _step_summary(env: dict[str, str]) -> None:
    console.print("\n[bold]Step 9 / 9 — Summary[/bold]")

    llm_count = sum(bool(env.get(k)) for k in [
        "NVIDIA_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
        "OPENAI_API_KEY", "PERPLEXITY_API_KEY",
    ])

    t = Table(box=box.SIMPLE)
    t.add_column("Item",   style="cyan", width=28)
    t.add_column("Status", width=40)

    t.add_row("Agent name",       env.get("AGENT_NAME", "—"))
    t.add_row("Base wallet",      (env.get("EVM_WALLET") or "not set")[:42])
    t.add_row("Solana wallet",    env.get("SOL_WALLET") or "not set")
    t.add_row("Superteam",        "✅ registered" if env.get("SUPERTEAM_API_KEY") else "⚠ not registered")
    t.add_row("LLM providers",    f"{llm_count} configured")
    t.add_row("Claude Code skill","✅ installed" if (_SKILL_DST / "SKILL.md").exists() else "⚠ missing")
    t.add_row(".env file",        str(_ENV_FILE))

    console.print(Panel(t, title="[bold green]Installation Complete[/bold green]", border_style="green"))

    console.print("\n[bold yellow]📋 One remaining manual step (requires your GitHub account):[/bold yellow]")
    console.print(
        "\n  1. Fork [cyan]https://github.com/Echolonius/echo-earning-agent[/cyan] on GitHub\n"
        "  2. Push the configured agent.mjs:\n\n"
        "     [dim]cd C:\\Users\\rishu\\.gemini\\antigravity\\scratch\\echo-earning-agent\n"
        "     git remote set-url origin https://github.com/YOUR_USERNAME/echo-earning-agent\n"
        "     git add agent.mjs\n"
        "     git commit -m \"configure: set my wallet addresses\"\n"
        "     git push[/dim]\n\n"
        "  3. Settings → Secrets → Actions → New secret:\n"
        f"     Name: [yellow]SUPERTEAM_API_KEY[/yellow]   Value: [dim]{env.get('SUPERTEAM_API_KEY', '<your key>')[:20]}...[/dim]\n\n"
        "  4. Actions tab → Enable workflows → Run [green]earning-agent[/green]"
    )

    if env.get("SUPERTEAM_CLAIM_CODE"):
        console.print(
            f"\n  [bold red]⚠  SAVE THIS CLAIM CODE (bookmark it):[/bold red]\n"
            f"  [yellow]{env['SUPERTEAM_CLAIM_URL']}[/yellow]"
        )

    console.print("\n[bold green]✅ Done! Run  python main.py  and choose option 2 to start the agent.[/bold green]\n")


# ─── Public entry point ───────────────────────────────────────────────────────

def run_installation() -> bool:
    """
    Run the full installation wizard.
    Returns True on success, False if a fatal prerequisite is missing.
    """
    console.print(Panel.fit(
        "[bold cyan]⚙  Penniless AI Agent — Complete Installation[/bold cyan]\n"
        "[dim]Sets up dependencies, wallet config, Superteam, LLM providers, and the Claude Code skill.[/dim]",
        border_style="cyan",
    ))

    # Step 1: prerequisites
    if not _step_prerequisites():
        return False

    # Load any existing .env values so we don't overwrite them
    env = _read_env()

    # Step 2: collect user inputs
    env = _step_collect_inputs(env)

    # Step 3: Python deps
    _step_install_deps()

    # Step 4: Superteam
    env = _step_register_superteam(env)

    # Step 5: write .env
    _step_write_env(env)

    # Step 6: Claude Code skill
    _step_install_skill()

    # Step 7: agent.mjs wallet config
    _step_configure_agent_mjs(env)

    # Step 8: test LLM providers
    _step_test_llm(env)

    # Step 9: summary
    _step_summary(env)

    return True
