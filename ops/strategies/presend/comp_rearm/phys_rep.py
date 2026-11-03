#!/usr/bin/env python3
"""physics table from comp_buys_*.pkl (MEASURED on tape)"""
import pickle, collections, numpy as np
D = "/home/moiz/sniper-data/comp_rearm"
R = [r for t in ("D2", "D3", "D4", "D5", "N", "r37") for r in pickle.load(open(f"{D}/comp_buys_{t}.pkl", "rb"))]
def q(a, p): return float(np.percentile(a, p)) if len(a) else float("nan")
print("| bot | buys | buy SOL p50 | curve SOL p50 | own sell found | sell delay ms p10/p50/p90 | same slot | sell SOL p50 | own sell drop p50/p90 | own sell alone >=12% | any 1-slot drop >=12% in 10 slots |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
by = collections.defaultdict(list)
for r in R: by[r["who"]].append(r); by["ALL"].append(r)
for w, rs in sorted(by.items(), key=lambda x: -len(x[1])):
    s = [r["sell"] for r in rs if r["sell"] and np.isfinite(r["sell"]["drop"])]
    dm = [x["dms"] for x in s]
    print(f"| {w} | {len(rs):,} | {q([r['sol']/1e9 for r in rs],50):.2f} | {q([r['vsol']/1e9 for r in rs],50):.0f} | {len(s)/len(rs):.0%} | {q(dm,10):.0f}/{q(dm,50):.0f}/{q(dm,90):.0f} | "
          f"{np.mean([x['same_slot'] for x in s]):.0%} | {q([x['sol']/1e9 for x in s],50):.2f} | {q([x['drop'] for x in s],50):.1%}/{q([x['drop'] for x in s],90):.1%} | "
          f"{np.mean([x['drop']>=0.12 for x in s]):.1%} | {np.mean([np.nan_to_num(r['maxdrop10'])>=0.12 for r in rs]):.1%} |")
# by buy size (all bots)
print("\n| buy SOL | buys | own sell alone >=12% | any >=12% 1-slot drop in 10 slots | after a >=1 SOL sell (backrun) share |")
print("|---|---|---|---|---|")
for lo, hi in ((0, .3), (.3, .7), (.7, 1.5), (1.5, 3), (3, 1e9)):
    rs = [r for r in R if lo <= r["sol"]/1e9 < hi]
    s = [r["sell"] for r in rs if r["sell"] and np.isfinite(r["sell"]["drop"])]
    print(f"| {lo}-{hi if hi<1e8 else '+'} | {len(rs):,} | {np.mean([x['drop']>=0.12 for x in s]):.1%} | {np.mean([np.nan_to_num(r['maxdrop10'])>=0.12 for r in rs]):.1%} | {np.mean([r['prev_big_sell'] for r in rs]):.0%} |")
print("\n| competitors in token (incl. this buy) | buys | any >=12% drop in 10 slots |")
print("|---|---|---|")
for n in (1, 2, 3, 4):
    rs = [r for r in R if (r["n_comp"] == n if n < 4 else r["n_comp"] >= 4)]
    print(f"| {n}{'+' if n==4 else ''} | {len(rs):,} | {np.mean([np.nan_to_num(r['maxdrop10'])>=0.12 for r in rs]):.1%} |")
