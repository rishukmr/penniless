"""Show content_type tags assigned to each live Superteam listing."""
import sys
sys.path.insert(0, '.')
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.bounty_scanner import scan_superteam

result = scan_superteam()
listings = result.get("open", [])
print(f"Source endpoint: {result.get('source_endpoint')}")
print(f"Total open: {len(listings)}\n")
for l in listings:
    ctype = l.get("content_type", "?")
    title = str(l.get("title", ""))[:60]
    reward = l.get("reward_usd", "?")
    token = l.get("token", "")
    icon = {"written": "✍️ ", "video": "🎥 ", "code": "💻 "}.get(ctype, "❓ ")
    print(f"{icon}[{ctype:8}] ${reward} {token} | {title}")
