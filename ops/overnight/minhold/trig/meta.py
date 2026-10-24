# Fetch public token metadata (uri from the launch record) for the group's tokens and a random sample of other launches. Read-only HTTP GETs.
import json, urllib.request, concurrent.futures as cf, random, re, os
MS = set(l.strip() for l in open("../g3/mints.txt") if l.strip())
L = {}
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        L[c["mint"]] = c
random.seed(7); others = random.sample([m for m in L if m not in MS], 400)
def get(m):
    fn = f"meta/{m}.json"
    if os.path.exists(fn): return
    u = L[m].get("uri") or ""
    if u.startswith("ipfs://"): u = "https://ipfs.io/ipfs/" + u[7:]
    try:
        d = urllib.request.urlopen(urllib.request.Request(u, headers={"user-agent": "Mozilla/5.0"}), timeout=20).read(200000)
        json.dump(dict(ok=True, body=d.decode("utf-8", "replace")), open(fn, "w"))
    except Exception as e: json.dump(dict(ok=False, err=str(e)[:100]), open(fn, "w"))
with cf.ThreadPoolExecutor(16) as ex: list(ex.map(get, [m for m in MS if m in L] + others))
json.dump(others, open("others.json", "w"))
ok = sum(1 for f in os.listdir("meta") if json.load(open("meta/" + f)).get("ok")); print("fetched ok:", ok, "of", len(os.listdir("meta")))
