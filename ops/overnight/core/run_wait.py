#!/usr/bin/env python3
# CONDITIONAL ENTRY (read-only): wait until D ms after the create; buy only if our engine has seen <= K outside txs by then;
# our buy lands at D + SEND ms; sell lands at 500 ms (or D+SEND+400 if later). Copy-list launches, 0.5 SOL.
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
from run_timed import L, O, fw, byb
GRID = [(D, K, SEND) for D in (2, 15, 30, 50) for K in (0, 1) for SEND in (35, 60, 70)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); outs = O[m]["outs"]; r = dict(m=m, bt=c["bt"], res={})
        for D, K, SEND in GRID:
            seen = sum(1 for o in outs if o[0] < D)
            if seen > K: continue
            Lm = D + SEND; ib, na = rp.place(tr, c, st, outs, Lm)
            if ib < 1: continue
            X = max(500, Lm + 400); isell = rp.place_ms(tr, c, st, outs, X, ib)
            r["res"][f"{D}_{K}_{SEND}"] = rp.flip(tr, ib, isell, 0.5)
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    for D, K, SEND in GRID:
        k = f"{D}_{K}_{SEND}"; v = [r["res"][k] for r in res if k in r["res"]]
        if not v: continue
        a = sum(r["res"][k] for r in res if k in r["res"] and r["bt"] < mid); s = sorted(v)
        print(f"decide at {D:2} ms if <= {K} outside seen, land +{SEND} ms: n {len(v):3} total {sum(v):+6.2f} (halves {a:+.2f}/{sum(v) - a:+.2f}) mean {statistics.mean(v):+.4f} win {sum(1 for x in v if x > 0) / len(v):.0%} w/o top5 {sum(s[:-5]):+.2f}")
