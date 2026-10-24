#!/usr/bin/env python3
# READ-ONLY, offline: which CREATE-TIME features predict BROAD demand (generic flow), i.e. the price rise from the
# post-bundle price to +10 s after removing CWiNFA and all 412 fast sniper wallets (decomp.json, bundled pool, both runs)?
# Shown per run so a feature has to hold in R1 and R2 separately.
import os, json, statistics, collections, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches()
D = json.load(open(os.path.join(HERE, "decomp.json"))); T = {x["mint"]: x for x in json.load(open(os.path.join(HERE, "table_slim.json")))}
K = "CWiNFA+fast+top10"
# deployer history inside our data: previous launch of the same deployer and its generic +10 s outcome (known ~10 s later)
seq = collections.defaultdict(list)
for m, c in L.items():
    if c.get("bt"): seq[c["user"]].append((c["bt"], m))
prev = {}
for d, v in seq.items():
    v.sort()
    for i, (bt, m) in enumerate(v):
        if i: prev[m] = (bt - v[i - 1][0], v[i - 1][1])
def feat(m):
    x = T.get(m) or {}; f = {}
    dv = x.get("dev_buy") or 0; f["dev buy"] = "1-2.5" if dv < 2.5 else ("2.5-4" if dv < 4 else "4+")
    g = x.get("glued_n") or 0; f["glued txs"] = str(min(g, 4))
    h = x.get("uri_host") or ""; f["launcher"] = "J7Tracker" if "j7tracker" in h else ("Uxento" if "uxento" in h else ("pump.fun IPFS" if ("ipfs" in h or h.startswith(("bafkrei", "Qm"))) else "other"))
    p = prev.get(m)
    if p is None: f["deployer's previous launch"] = "first seen"
    else:
        gap, pm = p; q = D.get(pm)
        f["gap since previous launch"] = "<1 min" if gap < 60 else ("1-10 min" if gap < 600 else ("10-60 min" if gap < 3600 else ">1 h"))
        if q: f["deployer's previous launch"] = "rose (generic +10 s > 1.05)" if q[K]["10s"] > 1.05 else ("fell (< 0.95)" if q[K]["10s"] < 0.95 else "flat")
        else: f["deployer's previous launch"] = "not in pool"
    f["create tip"] = "none" if not x.get("create_tips") else ("<0.002" if x["create_tips"] < 0.002 else ("0.002-0.005" if x["create_tips"] < 0.005 else ">=0.005"))
    f["X link"] = str(x.get("has_tw")); f["CWiNFA attempted"] = str(D[m]["att"])
    return f
rows = [(m, v, feat(m)) for m, v in D.items()]
out = [f"bundled pool: {len(rows)} launches; generic +10 s = price at +10 s / post-bundle price with CWiNFA + 412 fast sniper wallets removed",
       "per feature value: R1 median (share up, n) | R2 median (share up, n)"]
names = sorted({k for _, _, f in rows for k in f})
for k in names:
    vals = sorted({f.get(k) for _, _, f in rows if f.get(k) is not None})
    for val in vals:
        cells = []
        for run in ("R1", "R2"):
            xs = [v[K]["10s"] for m, v, f in rows if f.get(k) == val and v["run"] == run]
            cells.append(f"{statistics.median(xs):.3f} ({sum(x > 1 for x in xs) / len(xs):.0%}, n {len(xs)})" if len(xs) >= 20 else f"n {len(xs)}")
        out.append(f"  {k:28} {str(val):30} R1 {cells[0]:24} | R2 {cells[1]}")
open(os.path.join(HERE, "sel_generic.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
