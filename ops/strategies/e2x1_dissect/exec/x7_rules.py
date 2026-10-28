#!/usr/bin/env python3
"""Q3: fit simple exit rules on his D1 lots (tape replay, curve maths; exit at the curve state right after the trade that fires the rule —
optimistic: assumes landing before the next trade). Every rule also has his 1800 s timeout. Score: P&L (same costs as his) and
'match' = share of lots where the rule's exit slot is within +-2 slots of his real exit. Rules:
 TRAIL z (sell when price <= peak*(1-z)); ACT a TRAIL z (trail only after price >= entry*a); TP x; SL y; FLOW k (k slots with no outside buy);
 SELLAFTER s (first outside sell >= s SOL after >= m slots); combinations. Out: x7.txt"""
import sys, pickle, itertools
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
R = [r for r in pickle.load(open(f"{X.X}/x4.pkl", "rb")) if r["sells"] and not r["swap"] and not r["is_open"]]
K = 30.0 * 1073000000000000
def sell(v, tok): return v * tok / (K / v + tok)
TO = int(1800 / 0.212)
def run(r, rule):
    v0 = r["v0"]; peak = v0; last_buy = r["s"]; s0 = r["sells"][0]; gross_his = s0["net"] / (1 - (r["fbps"] + r["cbps"]) / 1e4); after = False; v = v0
    for p in r["path"]:
        if p[6]: after = True; continue
        # flow-stop check happens at slot boundaries before this trade
        if rule[0] == "FLOW" and p[0] - last_buy >= rule[1] and p[0] - r["s"] >= rule[2]:
            return last_buy + rule[1], v + (gross_his if after else 0)
        if p[0] - r["s"] >= TO: return r["s"] + TO, v + (gross_his if after else 0)
        v = p[5]; vv = v + (gross_his if after else 0)
        if p[3]: last_buy = p[0]
        peak = max(peak, vv); rr = (vv / v0) ** 2; dd = (vv / peak) ** 2; rp = (peak / v0) ** 2; ds = p[0] - r["s"]
        k = rule[0]
        if k == "TRAIL" and dd <= 1 - rule[1] and rp >= rule[2]: return p[0], vv
        if k == "TPSL" and (rr >= rule[1] or rr <= rule[2]): return p[0], vv
        if k == "SELLAFTER" and (not p[3]) and p[4] >= rule[1] and ds >= rule[2]: return p[0], vv
        if k == "TRAILSL" and ((dd <= 1 - rule[1] and rp >= rule[2]) or rr <= rule[3]): return p[0], vv
        if k == "TIME" and ds >= rule[1]: return p[0], vv
        if k == "SELLINTO" and p[3] and p[4] >= rule[1] and rr >= rule[2]: return p[0], vv
        if k == "SELLINTOSL" and ((p[3] and p[4] >= rule[1] and rr >= rule[2]) or rr <= rule[3]): return p[0], vv
    return (r["path"][-1][0] if r["path"] else r["s"]), v + (gross_his if after else 0)
rules = [("TRAIL", z, a) for z in (.05, .1, .15, .2, .3) for a in (1.0, 1.1, 1.2, 1.3, 1.5)] + \
        [("TPSL", x, y) for x in (1.2, 1.3, 1.5, 2.0, 3.0) for y in (.5, .7, .8, .9)] + \
        [("FLOW", k, m) for k in (5, 10, 25, 50, 100) for m in (0, 10, 50)] + \
        [("SELLAFTER", s, m) for s in (.1, .3, .5, 1, 2) for m in (0, 10, 50, 200)] + \
        [("TRAILSL", z, a, y) for z in (.1, .15, .2) for a in (1.1, 1.2) for y in (.7, .8)] + [("TIME", t) for t in (5, 50, 200, 1000)] + \
        [("SELLINTO", b, x) for b in (.3, .5, 1, 2) for x in (1.0, 1.1, 1.2, 1.5)] + [("SELLINTOSL", b, x, y) for b in (.3, .5, 1) for x in (1.1, 1.2) for y in (.7, .8)]
if len(sys.argv) > 1 and sys.argv[1] == "into": rules = [r for r in rules if r[0].startswith("SELLINTO")]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
for D in ("D1", "D0"):
    RR = [r for r in R if r["day"] == D]
    act = sum(r["pnl"] for r in RR)
    P(f"===== {D}: {len(RR)} curve-sold lots, actual P&L {act:+.3f}")
    res = []
    for rule in rules:
        tot = 0.0; m = 0; m10 = 0; early = 0
        for r in RR:
            s0 = r["sells"][0]; fees = (r["fbps"] + r["cbps"]) / 1e4
            xs, v = run(r, rule)
            tot += r["pnl"] - s0["net"] + sell(v, r["tok"]) * (1 - fees)
            m += abs(xs - s0["s"]) <= 2; m10 += abs(xs - s0["s"]) <= 10; early += xs < s0["s"] - 2
        res.append((tot, m / len(RR), m10 / len(RR), early / len(RR), rule))
    P("  top 12 by P&L:")
    for x in sorted(res, key=lambda x: -x[0])[:12]: P(f"    {str(x[4]):34} P&L {x[0]:+8.3f}  match+-2 {100*x[1]:4.1f}%  +-10 {100*x[2]:4.1f}%  rule earlier {100*x[3]:3.0f}%")
    P("  top 8 by match:")
    for x in sorted(res, key=lambda x: -x[1])[:8]: P(f"    {str(x[4]):34} P&L {x[0]:+8.3f}  match+-2 {100*x[1]:4.1f}%  +-10 {100*x[2]:4.1f}%  rule earlier {100*x[3]:3.0f}%")
open(f"{X.X}/x7" + ("b" if len(sys.argv) > 1 else "") + ".txt", "w").write("\n".join(out) + "\n")
