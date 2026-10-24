#!/usr/bin/env python3
# Fetch public metadata JSON for every launch whose uri is NOT a generic IPFS gateway (tweet-to-token launchers etc.), all runs R1–R4.
# Keeps only: name, symbol, twitter, website, createdOn, description (300 chars). Read-only HTTP GETs, 24 threads, resumable.
import json, re, os, sys, urllib.request, concurrent.futures as cf, time
dom = lambda u: (re.sub(r"^https?://", "", u or "").split("/")[0] or "none")
OUT = "meta.jsonl"; done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["m"])
        except Exception: pass
todo = []
for run, tag in (("run_20261021_2207", "R1"), ("run_20261022_1543", "R2"), ("run_20261023_1426", "R3"), ("run_20261024_1425", "R4")):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        d = dom(c.get("uri"))
        if c["mint"] in done or d.startswith("ipfs") or d in ("none", "pump.mypinata.cloud", "gateway.pinata.cloud"): continue
        todo.append((c["mint"], c["uri"], tag, d))
print("to fetch:", len(todo), flush=True)
def get(x):
    m, u, tag, d = x
    for i in range(2):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers={"user-agent": "Mozilla/5.0"}), timeout=10).read(100000)
            j = json.loads(b.decode("utf-8", "replace"))
            return dict(m=m, run=tag, host=d, ok=True, twitter=str(j.get("twitter") or "")[:200], website=str(j.get("website") or "")[:200],
                        createdOn=str(j.get("createdOn") or "")[:60], desc=str(j.get("description") or "")[:300])
        except Exception as e: err = str(e)[:60]; time.sleep(0.5)
    return dict(m=m, run=tag, host=d, ok=False, err=err)
n = 0
with open(OUT, "a") as f, cf.ThreadPoolExecutor(24) as ex:
    for r in ex.map(get, todo):
        f.write(json.dumps(r) + "\n"); n += 1
        if n % 5000 == 0: print(n, flush=True)
print("DONE", n)
