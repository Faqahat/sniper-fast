#!/usr/bin/env python3
"""LIM step 14 (read-only): haqq's DIP fills split by whether he bought the same token AGAIN while the lot was open ('later add',
known only after entry). Measured lot P&L (FIFO, before tx costs) and the exact replay of the lot alone (his rows removed,
timer exits h2/h5/h15/h30) - per price-paid bucket and per day.
Out: data/lim/l14.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
H2 = pickle.load(open(f"{OUT}/hctx2.pkl", "rb"))
bym = collections.defaultdict(list)
for r in H2:
    if r["ok"]: bym[r["mint"]].append((r["s"], r["i"]))
F = [r for r in pickle.load(open(f"{OUT}/hfeat.pkl", "rb")) if not r["mayhem"]]
for r in F:
    end = r["close"] if r.get("close") is not None else 10 ** 12
    r["later_add"] = any((s, i) > (r["s"], r["i"]) and s <= end for s, i in bym[r["mint"]])
pc = lambda v, f: 100 * sum(f(r) for r in v) / sum(r["spend"] for r in v) if v else float("nan")
P("# haqq DIP fills: single-lot vs later-added positions (%/SOL before tx costs; his tx cost ~0.24%/SOL at 0.33 SOL)")
P("| price paid vs post-dump | later add | lots | SOL | actual %/SOL | replay h2 | h5 | h15 | h30 | actual by day (D0..D6) |"); P("|---|---|---|---|---|---|---|---|---|---|")
for nm, sel in (("pr <= 1.05", lambda r: r["pr"] <= 1.05), ("pr 1.05-1.10", lambda r: 1.05 < r["pr"] <= 1.10), ("pr > 1.10", lambda r: r["pr"] > 1.10), ("pr > 1.05", lambda r: r["pr"] > 1.05)):
    for la in (False, True):
        v = [r for r in F if sel(r) and r["later_add"] == la]
        days = " ".join(f"{pc([r for r in v if r['day'] == d], lambda r: r['lot_pnl']):+.1f}" for d in range(7))
        P(f"| {nm} | {'yes' if la else 'no'} | {len(v)} | {sum(r['lot_pnl'] for r in v):+.2f} | {pc(v, lambda r: r['lot_pnl']):+.2f} | " +
          " | ".join(f"{pc(v, lambda r, h=h: r['rep'][(h, 1.0)]):+.2f}" for h in (2, 5, 15, 30)) + f" | {days} |")
open(f"{OUT}/l14.txt", "w").write("\n".join(out) + "\n")
