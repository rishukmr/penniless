import sys, requests
sys.path.insert(0, '.')
from src.config import cfg
cfg.reload()

r = requests.get(
    'https://superteam.fun/api/listings?take=50&type=bounty&status=open',
    headers={'Authorization': f'Bearer {cfg.SUPERTEAM_API_KEY}'},
    timeout=12
)
data = r.json()
print(f"Total listings: {len(data)}\n")
for l in data[:12]:
    title = str(l.get("title",""))[:60]
    ltype = l.get("type","?")
    reward = l.get("rewardAmount","?")
    token = l.get("token","?")
    skills = l.get("skills", [])
    deadline = str(l.get("deadline",""))[:10]
    print(f"[{ltype}] {title}")
    print(f"  Reward: {reward} {token} | Skills: {skills} | Deadline: {deadline}")
    print()
