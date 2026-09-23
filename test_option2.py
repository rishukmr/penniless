"""
Manual test of Option 2 (Run the Software) flow.
Tests each step individually so we can see exactly where it breaks.
"""
import sys, os, traceback
sys.path.insert(0, '.')

# UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("=" * 60)
print("STEP 1: Config validation")
print("=" * 60)
try:
    from src.config import cfg
    cfg.reload()
    issues = cfg.validate()
    if issues:
        for i in issues:
            print(f"  ERROR: {i}")
    else:
        print("  OK - no validation issues")
    print(f"  NVIDIA key set : {bool(cfg.NVIDIA_API_KEY)}")
    print(f"  Gemini key set : {bool(cfg.GEMINI_API_KEY)}")
    print(f"  Groq key set   : {bool(cfg.GROQ_API_KEY)}")
    print(f"  EVM wallet     : {cfg.EVM_WALLET[:12]}..." if cfg.EVM_WALLET else "  EVM wallet: NOT SET")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("STEP 2: LLM client refresh")
print("=" * 60)
try:
    from src.llm_client import llm
    llm._refresh()
    print(f"  Active: {llm.active_summary()}")
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("STEP 3: Wallet monitor")
print("=" * 60)
try:
    from src.wallet_monitor import get_status
    status = get_status()
    print(f"  Base USDC  : {status.get('base_usdc')}")
    print(f"  Sol USDC   : {status.get('sol_usdc')}")
    print(f"  Total      : {status.get('total_usd')}")
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("STEP 4: Bounty scanner - scan_all()")
print("=" * 60)
try:
    from src.bounty_scanner import scan_all
    results = scan_all(verbose=True)
    all_opps = results.get("all", [])
    print()
    print(f"  Total opportunities: {len(all_opps)}")
    # Per-source (skip non-list values like 'total' int and 'all' list we already counted)
    for source, items in results.items():
        if source in ("all", "total"):
            continue
        if isinstance(items, list):
            print(f"  {source}: {len(items)} items")
        elif isinstance(items, dict):
            count = len(items.get("open", []))
            ep = items.get("source_endpoint", "")
            print(f"  {source}: {count} open listings [via {ep}]")
    if all_opps:
        print()
        print("  First 3 opportunities:")
        for o in all_opps[:3]:
            src = o.get("source", "?")
            title = str(o.get("title", o.get("slug", "?")))[:55]
            reward = o.get("reward_usd", "?")
            print(f"    [{src}] {title} | ${reward}")
        print("  OK - opportunities found!")
    else:
        print("  WARNING: No opportunities found (all sources returned 0 results)")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("STEP 5: LLM propose_task (quick 1-msg test, NO full scan)")
print("=" * 60)
try:
    from src.llm_client import llm
    # Quick test message - not full proposal, just verify LLM responds
    reply = llm.chat(
        messages=[{"role": "user", "content": "Say READY in one word."}],
        max_tokens=300,   # DeepSeek needs headroom (thinking tokens), min ~100
        silent=True
    )
    print(f"  LLM reply: {reply.strip()[:50]}")
    print("  OK - LLM responding")
except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("ALL STEPS DONE - review results above")
print("=" * 60)
