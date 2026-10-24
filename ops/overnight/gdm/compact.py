#!/usr/bin/env python3
# compact comparison of gsum JSON outputs: PRO-cost totals per landing x variant for one exit, + robustness of one cell
import sys, json
f, ex = sys.argv[1], sys.argv[2]; S = json.load(open(f))
V = ("slip", "proafter_slip", "nosnip")
print(f"{'list':14s} | " + " | ".join(f"L{L} fills  slip  pro-af  nosnip" for L in ("75", "45", "30")))
for nm, rows in S.items():
    cells = []
    for L in ("75", "45", "30"):
        r = {x["var"]: x for x in rows if x["L"] == L and x["ex"] == ex}
        cells.append(f"{r['slip']['fills']:3d}/{r['slip']['att']:3d} {r['slip']['pro']:+5.2f} {r['proafter_slip']['pro']:+6.2f} {r['nosnip']['pro']:+6.2f}")
    print(f"{nm:14s} | " + " | ".join(cells))
print(f"robustness, {ex}, pro buys after us removed + slippage (proafter_slip), PRO costs [today-cost total | median/fill | win | w/o top5 | halves]")
for nm, rows in S.items():
    cells = []
    for L in ("75", "45", "30"):
        r = next(x for x in rows if x["L"] == L and x["ex"] == ex and x["var"] == "proafter_slip")
        cells.append(f"L{L} {r['cur']:+5.2f} {r['med']:+.3f} {r['win']:.0%} {r['wo5']:+5.2f} {r['h1']:+.2f}/{r['h2']:+.2f}")
    print(f"{nm:14s} | " + " | ".join(cells))
