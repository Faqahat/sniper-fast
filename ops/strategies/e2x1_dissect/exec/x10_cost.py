#!/usr/bin/env python3
"""Q4 execution cost per lot (MEASURED): his buy fee+tip, sell fee+tip, failed copies, rent net; vs ours per fill (FRA r27/r28, AMS r28 records).
Out: x10.txt"""
import sys, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for D in ("D1", "D0"):
    L = [l for l in X.lots() if l["day"] == D]
    P(f"===== {D} his lots {len(L)} (mSOL per lot)")
    for b in ("ALL", "FRESH", "MINUTE", "OLD"):
        v = [l for l in L if b == "ALL" or l["bot"] == b]; n = len(v)
        f = lambda k: 1000 * sum(l[k] for l in v) / n
        tot = f("buy_txfee") + f("buy_tip") + f("sell_txfee") + f("sell_tip") + f("fail_fee")
        P(f"  {b:6} n={n:4} buy fee {f('buy_txfee'):.3f} tip {f('buy_tip'):.3f} | sell fee {f('sell_txfee'):.3f} tip {f('sell_tip'):.3f} | failed {f('fail_fee'):.3f} | "
          f"TOTAL {tot:.3f} mSOL  (rent net {f('rent_x')-f('rent_c'):+.3f}, curve realloc {f('curve_extend'):.3f})  = {100*tot/1000/np.mean([l['cost'] for l in v]):.2f}% of buy size")
    tips = sum(l["buy_tip"] + l["sell_tip"] for l in L); fees = sum(l["buy_txfee"] + l["sell_txfee"] + l["fail_fee"] for l in L)
    P(f"  day totals: tips {tips:.4f} SOL, tx fees incl failed {fees:.4f} SOL, together {tips+fees:.4f} SOL vs trading P&L {sum(l['pnl'] for l in L):+.3f}")
o = pickle.load(open(f"{X.X}/x2.pkl", "rb"))["cost"]
P("===== OURS (mSOL per fill, run records)")
for run, c in o.items():
    n = c["closes"]
    b = (c["buy_fee"] + c["buy_tip"]) / n / 1e6; s = (c["sell_fee"] + c["sell_tip"]) / n / 1e6; fl = c["fail_fee"] / n / 1e6; a = c.get("ata_fee", 0) / n / 1e6
    P(f"  {run} fills {n}: buy {b:.3f} | sell {s:.3f} | failed tries {fl:.3f} ({c['tries_failed']/n:.0f} per fill) | ata close {a:.3f} | TOTAL {b+s+fl+a:.3f} mSOL; 450 mSOL size -> {100*(b+s+fl+a)/450:.2f}%")
open(f"{X.X}/x10.txt", "w").write("\n".join(out) + "\n")
