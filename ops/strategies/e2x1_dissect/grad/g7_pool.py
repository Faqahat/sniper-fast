#!/usr/bin/env python3
"""grad agent, step 7: what happens on PumpSwap right after migration (all normal SOL-quoted pump graduations).
Per migration: completion -> migration slots; pool price at migration + N slots vs the opening price; buy/sell SOL and number of
buy txs in the first slots (competition at pool open); fee rate. Prints distribution tables per PKT day."""
import numpy as np, collections
from glib import Tape, last_before, pool_state_after, pool_fee, pday

T = Tape()
NS = [2, 5, 10, 20, 48, 100, 200]
rows = []
for m, mg in T.mig.items():
    if not mg["quote"].startswith("So111"): continue
    cr = T.cr.get(m)
    if cr is None or cr.get("mayhem"): continue
    P = T.pool_events(mg["pool"])
    p0 = mg["pquote"] / mg["pbase"]
    r = dict(mint=m, day=pday(mg["bt"]), n_ev=len(P))
    c = T.cmp.get(m); r["cmp_to_mig"] = mg["slot"] - c["slot"] if c else None
    for n in NS:
        k = last_before(P, mg["slot"] + n, 0)
        b, q = pool_state_after(P, k, mg); r[f"p{n}"] = (q / b) / p0
    w = P[(P["slot"] >= mg["slot"]) & (P["slot"] <= mg["slot"] + 5)]
    r["buys5"] = int((w["buy"] == 1).sum()); r["buy_sol5"] = float(w["quote"][w["buy"] == 1].sum()) / 1e9
    r["sell_sol5"] = float(w["quote"][w["buy"] == 0].sum()) / 1e9
    w2 = P[(P["slot"] >= mg["slot"]) & (P["slot"] <= mg["slot"] + 1)]
    r["buyers_0_1"] = len(set(w2["signer"][w2["buy"] == 1].tolist()))
    r["fee"] = pool_fee(P, 0) if len(P) else np.nan
    rows.append(r)
print("normal SOL graduations:", len(rows))
cm = np.array([r["cmp_to_mig"] for r in rows if r["cmp_to_mig"] is not None])
print("completion -> migration slots: pct 10/50/90/99:", np.percentile(cm, [10, 50, 90, 99]))
print("fee rate at open: median", np.nanmedian([r["fee"] for r in rows]))
print("price at mig+N / opening price (median, mean, share > 1):")
for n in NS:
    x = np.array([r[f"p{n}"] for r in rows])
    print(f"  N={n:3d}: median {np.median(x):.3f}  mean {x.mean():.3f}  >1: {(x > 1).mean():.0%}  p10 {np.percentile(x, 10):.3f}  p90 {np.percentile(x, 90):.3f}")
print("competition at open (first 5 slots): buys median", np.median([r["buys5"] for r in rows]), "| buy SOL median", round(np.median([r["buy_sol5"] for r in rows]), 2),
      "| sell SOL median", round(np.median([r["sell_sol5"] for r in rows]), 2), "| distinct buyer signers in slots 0-1 median", np.median([r["buyers_0_1"] for r in rows]))
by = collections.defaultdict(list)
for r in rows: by[r["day"]].append(r)
print("per day: graduations, median p48, mean p48")
for d in sorted(by): print(" ", d, len(by[d]), round(np.median([r["p48"] for r in by[d]]), 3), round(np.mean([r["p48"] for r in by[d]]), 3))
import pickle; pickle.dump(rows, open("/home/moiz/sniper-data/e2x1_dissect/grad/pool_open.pkl", "wb"))
