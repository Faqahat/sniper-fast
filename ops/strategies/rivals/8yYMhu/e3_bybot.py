#!/usr/bin/env python3
"""8yYMhu e3 (read-only): exit shape per bot (MAIN-75 vs TIMER6-50) from exitpath.pkl: hold histogram, hazard by slot and by the position
return at the end of the previous slot, timeout cost; plus a what-if on MAIN-75: cut the timeout losers earlier. Out: DATA/e3.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
EP = pickle.load(open(f"{X.D}/exitpath.pkl", "rb")); L = {l["lot_id"]: l for l in pickle.load(open(f"{X.D}/lots.pkl", "rb"))}
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for b_ in ("MAIN-75", "TIMER6-50"):
    E = [e for e in EP if e["lot"] in L and (("TIMER6-50" if L[e["lot"]]["sol_curve"] < 0.62 else "MAIN-75") == b_)]
    h = np.array([e["hold"] for e in E]); c = collections.Counter(h.tolist())
    P(f"\n== {b_}: lots {len(E)}; hold p10/25/50/75/90 " + "/".join(f"{X.pct(h,q):.0f}" for q in (10, 25, 50, 75, 90)))
    P("   hold histogram (top): " + ", ".join(f"{k}:{v}" for k, v in c.most_common(14)))
    cnt = collections.Counter(); hz = collections.Counter()
    for e in E:
        for x in range(1, e["hold"] + 1):
            cnt[x] += 1; hz[x] += (x == e["hold"])
    P("   hazard by slot: " + "  ".join(f"{x}:{100*hz[x]/cnt[x]:.0f}%" for x in (1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 30, 40, 50, 55, 60, 61) if cnt[x] >= 30))
    Bk = [(-9, -.08), (-.08, -.02), (-.02, .02), (.02, .08), (.08, 9)]
    row = []
    for lo, hi in Bk:
        a = b = 0
        for e in E:
            for x in range(7, min(e["hold"], 59) + 1):
                rp = e["path"][x - 1][1]
                if lo <= rp < hi: a += 1; b += (x == e["hold"])
        row.append(f"[{100*lo:+.0f}%,{100*hi:+.0f}%) {100*b/max(a,1):.1f}% (n {a})")
    P("   slots 7-59: P(sell next slot) by return at end of previous slot: " + "; ".join(row))
    pn = np.array([L[e["lot"]]["pnl_cash"] for e in E])
    to = (h >= 60) & (h <= 62)
    P(f"   timeouts (60-62 slots): {to.sum()} lots ({100*to.mean():.0f}%), net {pn[to].sum():+.2f} SOL, win {100*np.mean(pn[to]>0):.0f}%; non-timeout net {pn[~to].sum():+.2f}")
# what-if MAIN-75: sell at slot 20 if return < X (curve value), else keep his exit
E = [e for e in EP if e["lot"] in L and L[e["lot"]]["sol_curve"] >= 0.62]
for cut, thr in ((10, -0.05), (20, -0.05), (20, 0.0), (30, -0.05)):
    d = 0.0; n = 0
    for e in E:
        if e["hold"] > cut and e["path"][cut][1] < thr:
            d += (e["path"][cut][1] - e["ret_exit"]) * e["cost"]; n += 1
    P(f"what-if MAIN-75: sell at slot {cut} when the position is below {100*thr:+.0f}% (else his exit): {n} lots changed, P&L change {d:+.2f} SOL (curve, before fees saved)")
open(f"{X.D}/e3.txt", "w").write("\n".join(out) + "\n")
