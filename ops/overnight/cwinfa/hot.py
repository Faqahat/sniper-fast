#!/usr/bin/env python3
# READ-ONLY, offline: a generic (no copying) selection idea from the broad-demand features: bundled launches whose
# deployer's PREVIOUS launch rose on generic flow (+10 s price > 1.05x post-bundle with CWiNFA + fast snipers removed,
# outcome known before the new launch), not a relaunch within 60 s, dev buy < 4 SOL. Traded with our guard at 45 / 75 ms,
# 0.5 SOL, holds eos / 1 s / 5 s / 10 s / 30 s; base / generic-only / generic + slip (generic.json, R2 timelines).
import os, sys, json, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); G = json.load(open(os.path.join(HERE, "generic.json"))); D = json.load(open(os.path.join(HERE, "decomp.json")))
R = json.load(open(os.path.join(HERE, "replay_all.json")))
K = "CWiNFA+fast+top10"
seq = collections.defaultdict(list)
for m, c in L.items():
    if c.get("bt"): seq[c["user"]].append((c["bt"], m))
prev = {}
for d, v in seq.items():
    v.sort()
    for i, (bt, m) in enumerate(v):
        if i: prev[m] = (bt, v[i - 1][0], v[i - 1][1])
def hot(m):
    p = prev.get(m)
    if not p: return False
    bt, pbt, pm = p
    if bt - pbt < 60 or pm not in D: return False
    return D[pm][K]["10s"] > 1.05 and R[m]["dev"] < 4 and R[m]["dev"] >= 1 and R[m]["glued"] >= 1
ms = sorted([m for m in G if m in R and hot(m)], key=lambda m: R[m]["bt"])
lines = [f"hot-deployer launches (R2, our timeline): {len(ms)}"]
for Lm in (45, 75):
    v = [(R[m]["bt"], G[m].get(str(Lm), "x")) for m in ms]; v = [(t, x) for t, x in v if x != "x"]
    if not v: continue
    t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2; fills = sum(1 for _, x in v if x)
    for k in ("eos", "t1", "t5", "t10", "t30"):
        cells = []
        for name in ("base", "generic", "generic_slip"):
            xs = [(t, (x[name][k] if x and x.get(name) else (-0.005 if x is None else 0.0))) for t, x in v]
            tot = sum(y for _, y in xs); a = sum(y for t, y in xs if t < mid)
            cells.append(f"{name} {tot:+6.2f} ({a:+.2f}/{tot - a:+.2f})")
        lines.append(f"  @ {Lm} ms exit {k:4}: fills {fills}/{len(v)} | " + " | ".join(cells))
open(os.path.join(HERE, "hot.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
