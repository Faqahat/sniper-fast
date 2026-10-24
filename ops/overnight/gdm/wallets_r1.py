#!/usr/bin/env python3
# leakage check helper: fast-sniper wallet list from R1 ONLY (same definition as core/gf_stage1.py: >= 5 launches whose first
# buy was in the create slot or the next, and >= 50% of its launches) -> gdm/sniper_r1.json
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches()
todo = [m for m, c in L.items() if c.get("bt") and c["run"] == "R1" and "InitializeMayhemState" not in (c.get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R1", b, byb[b]); W = collections.defaultdict(lambda: [0, 0])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c); first = {}
        for t in tr:
            if t["user"] in st["insiders"] or not t["buy"]: continue
            if t["user"] not in first: first[t["user"]] = t["s"] - S
        for u, d in first.items(): W[u][0] += 1; W[u][1] += 1 if d <= 1 else 0
    return dict(W)
if __name__ == "__main__":
    W = collections.defaultdict(lambda: [0, 0])
    with Pool(6) as p:
        for w in p.imap_unordered(work, sorted(byb)):
            for u, v in w.items(): W[u][0] += v[0]; W[u][1] += v[1]
    S1 = sorted(u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0])
    Wall = json.load(open("/home/moiz/sniper/ops/overnight/core/gf_wallets.json")); SA = {u for u, v in Wall.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
    json.dump(S1, open("/home/moiz/sniper/ops/overnight/gdm/sniper_r1.json", "w"))
    print(f"R1-only snipers {len(S1)}; full-data snipers {len(SA)}; both {len(SA & set(S1))}")
