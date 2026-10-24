#!/usr/bin/env python3
# READ-ONLY replay of a GENERIC-flow idea learned from dKMjeG (owner rule: no profit from specific bots): enter AFTER the
# fast-sniper burst (first trade after create slot + k), 0.5 SOL, exit all at +2 / +5 / +15 s, with every FAST sniper buy
# after our entry removed (only generic flow remains) and the follower slippage limits applied. Sets: launches its model
# would pick (R1-trained, R2 test, top 2% / 5%), its actual attempts (oracle), all R2 launches (reference).
import sys, json, collections, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
import numpy as np
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"; HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"
L = rp.load_launches(); C = json.load(open(f"{HERE}/coll.json")); ATT = {m for m, v in C.items() if "dk" in v}
FAST = set(json.load(open(f"{HERE}/fast_snipers.json"))); SLIP = rp.load_slip()
R = json.load(open(f"{HERE}/sel_rows.json")); src = open(f"{HERE}/sel2.py").read(); g = {}
exec(src[src.index("def f(r):"):src.index("X = np.array")], {"math": math}, g); exec(src[src.index("def fit("):src.index("tr = run ==")], {"np": np}, g)
X = np.array([g["f"](r) for r in R]); y = np.array([r["att"] for r in R], dtype=float); run = np.array([r["run"] for r in R])
w, mu, sd = g["fit"](X[run == "R1"], y[run == "R1"]); s2 = g["pred"](w, mu, sd, X[run == "R2"]); R2m = [r["m"] for r in R if r["run"] == "R2"]
SETS = {"model top 2%": {m for m, sc in zip(R2m, s2) if sc >= np.quantile(s2, 0.98)}, "model top 5%": {m for m, sc in zip(R2m, s2) if sc >= np.quantile(s2, 0.95)},
        "its attempts (oracle)": {m for m in ATT if m in L and L[m]["run"] == "R2"}, "all R2 launches": {m for m in R2m}}
ALLM = {m for s in SETS.values() for m in s if "InitializeMayhemState" not in (L[m].get("ixn") or [])}
byb = collections.defaultdict(set)
for m in ALLM: byb[rp.bucket(m)].add(m)
EX = [rp.R(f"t{t}", [(1.0, ("t", t))], t + 1) for t in (2, 5, 15)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); r = {}
        for k in (1, 2):
            k0 = next((i for i, t in enumerate(tr) if t["s"] > c["slot"] + k), None)
            if k0 is None or k0 < 1: continue
            o = rp.sim(tr, c, st, k0, 0.5, EX, fill_pen=0.015, drop_after=FAST | {W}, slip=SLIP)
            o2 = rp.sim(tr, c, st, k0, 0.5, EX, fill_pen=0.015)
            if o and o2: r[k] = {e: (o[e]["pnl"], o2[e]["pnl"]) for e in o}
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    for nm, sset in SETS.items():
        for k in (1, 2):
            v = [res[m][k] for m in sset if m in res and k in res[m]]
            if not v: continue
            print(f"{nm:22} enter after slot +{k} (n={len(v)}): " + " | ".join(f"exit {e}: generic-only {sum(x[e][0] for x in v):+.2f} (mean {sum(x[e][0] for x in v) / len(v):+.4f}) vs all flow {sum(x[e][1] for x in v):+.2f}" for e in ("t2", "t5", "t15")))
