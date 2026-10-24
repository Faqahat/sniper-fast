#!/usr/bin/env python3
# QUICK FLIP with a TIMED SELL placed like the buy (read-only, offline): buy lands at L ms after the create, sell lands
# at X ms after the create; both placed by our arrival-time model (everything our engine saw before is ahead).
import sys, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
LS = json.load(open("lists_cut1709.json"))
A = json.load(open("attempts.json"))
U = lambda d: any(LS.get(w, {}).get(d, 0) >= 1 for w in ("9Sh2fd", "DGmspi"))
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or []) and U(L[m]["user"])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
LANDS = (35, 45, 60, 75); SELLS = (120, 200, 300, 400, 500, 700, 900)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); r = dict(m=m, bt=c["bt"], res={})
        for Lm in LANDS:
            ib, na = rp.place(tr, c, st, O[m]["outs"], Lm)
            if ib < 1: continue
            for X in SELLS:
                if X <= Lm + 40: continue
                isell = rp.place_ms(tr, c, st, O[m]["outs"], X, ib)
                r["res"][f"{Lm}_{X}"] = rp.flip(tr, ib, isell, 0.5)
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    print(f"copy-list launches: {len(res)}; total PnL (SOL, 0.5 SOL/trade) for buy landing L ms x sell landing X ms after the create (halves)")
    print("   " + "".join(f"{'sell@' + str(X):>18}" for X in SELLS))
    for Lm in LANDS:
        cells = []
        for X in SELLS:
            k = f"{Lm}_{X}"; v = [r["res"][k] for r in res if k in r["res"]]
            a = sum(r["res"][k] for r in res if k in r["res"] and r["bt"] < mid)
            cells.append(f"{sum(v):+6.2f}({a:+.1f}/{sum(v) - a:+.1f})" if v else "-")
        print(f"L{Lm:<3}" + "".join(f"{c:>18}" for c in cells))
    json.dump(res, open("timed.json", "w"))
