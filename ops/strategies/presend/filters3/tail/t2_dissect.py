#!/usr/bin/env python3
"""TAIL t2: dissect every big loss (< -0.04) and big win (> +0.04) in DEV and VAL; group losses by cause (who sold into our hold).
Cause = the largest seller inside our hold (after our buy, before our sell landed): W whale/re-arm dumper, H another holder listed at
landing (>= 2%), X a wallet NOT listed (hidden / small holder) selling >= 1 SOL, N nobody sold >= 1 SOL (flat / drift / deep entry)."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
from tlib import *; from tfeat import feats, outcome
P = load()
rows = []
for d in P:
    F = feats(d); sells, buys = outcome(d, OURS)
    whale = F.get("whale") or ""
    listed = {h["w"][:8] for h in F.get("holders") or []}
    top = max(sells.items(), key=lambda kv: kv[1], default=(None, 0.0))
    u, s = top
    if s < 1.0: cause = "N"
    elif whale and u[:8] == whale[:8]: cause = "W"
    elif not F["has_ann"]: cause = "?"
    elif u[:8] in listed: cause = "H"
    else: cause = "X"
    rows.append({"run": d["rk"], "set": d["set"], "t": d["t"], "mint": d["mint"], "kind": F["kind"], "pnl": d["pnl"], "cause": cause,
                 "top_seller": u, "top_sol": s, "sell_sum": sum(sells.values()), "buy_sum": sum(buys.values()), "n_buyers": len(buys),
                 "F": {k: v for k, v in F.items() if k != "holders"}, "exit": (d.get("close") or {}).get("exit_why")})
json.dump(rows, open(f"{T}/dissect_rows.json", "w"))
def tab(sel, title):
    print(f"\n== {title}")
    for st in ("DEV", "VAL"):
        R = [r for r in rows if r["set"] == st and sel(r)]
        c = collections.defaultdict(lambda: [0, 0.0])
        for r in R: c[r["cause"]][0] += 1; c[r["cause"]][1] += r["pnl"]
        print(f"  {st}: n {len(R)} sum {sum(r['pnl'] for r in R):+.3f} | " + " | ".join(f"{k} {v[0]} {v[1]:+.3f}" for k, v in sorted(c.items())))
tab(lambda r: r["pnl"] < -0.04, "BIG LOSSES (< -0.04) by cause")
tab(lambda r: r["pnl"] > 0.04, "BIG WINS (> +0.04) by top in-hold seller class")
tab(lambda r: True, "ALL trades by top in-hold seller class")
for st in ("DEV", "VAL"):
    R = [r for r in rows if r["set"] == st]
    print(f"\n{st} by kind: " + " | ".join(f"{k} n{sum(1 for r in R if r['kind']==k)} {sum(r['pnl'] for r in R if r['kind']==k):+.3f} big-loss {sum(r['pnl'] for r in R if r['kind']==k and r['pnl']<-0.04):+.3f}" for k in ("t2", "rearm")))
# loss size distribution
for st in ("DEV", "VAL"):
    R = sorted(r["pnl"] for r in rows if r["set"] == st)
    print(st, "worst 10:", [round(x, 3) for x in R[:10]], "| best 5:", [round(x, 3) for x in R[-5:]])
