#!/usr/bin/env python3
"""Q3: his exit vs fixed-time exits on HIS lots (MEASURED tape, curve maths). Exit at chain-clock t = buy + dt: proceeds = curve sell of his
tokens at the curve state after the last trade with cc <= t (+ his own sell's SOL added back if that trade is after his real sell).
Our live rule = sell 200 ms after the fill (lands ~+2 slots: r27 example). P&L_cf = pnl - his real curve proceeds + cf proceeds (all
other costs kept). Graduated (PumpSwap) and open lots excluded. Out: x8.txt"""
import sys, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
R = pickle.load(open(f"{X.X}/x4.pkl", "rb")); LL = {l["lot_id"]: l for l in X.lots()}
K = 30.0 * 1073000000000000
def sell(v, tok): return v * tok / (K / v + tok)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
DT = [("200ms", 200), ("1 slot", 212), ("2 slots(=our 200ms+land)", 424), ("5 slots", 1060), ("1 s", 1000), ("3 s", 3000), ("10 s", 10000), ("30 s", 30000), ("60 s", 60000)]
for D in ("D1", "D0"):
    RR = [r for r in R if r["day"] == D and r["sells"] and not r["swap"] and not r["is_open"]]
    res = collections.defaultdict(list)
    for r in RR:
        l = LL[r["lot"]]; fees = (r["fbps"] + r["cbps"]) / 1e4; s0 = r["sells"][0]
        c0 = X.cc(r["s"], r["i"]); csell = X.cc(s0["s"], s0["i"]); gross_his = s0["net"] / (1 - fees)
        act = sell(([p for p in r["path"] if (p[0], p[1]) < (s0["s"], s0["i"])] or [(0, 0, 0, 0, 0, r["v0"])])[-1][5], r["tok"]) * (1 - fees)
        for lab, dt in DT:
            t = c0 + dt; v = r["v0"]; after = False
            for p in r["path"]:
                if X.cc(p[0], p[1]) > t: break
                if p[6]: after = True; continue
                v = p[5]
            vv = v + (gross_his if after else 0.0)
            cf = sell(vv, r["tok"]) * (1 - fees)
            res[lab].append(r["pnl"] - s0["net"] + cf)
        res["actual"].append(r["pnl"]); res["_bot"].append(r["bot"]); res["_lot"].append(r["lot"])
    bots = np.array(res["_bot"])
    P(f"===== {D}: {len(RR)} curve-sold lots (PumpSwap/open excluded)")
    hdr = f"  {'exit':26} {'ALL':>9} {'FRESH':>9} {'MINUTE':>9} {'OLD':>9}  win%  top5%-share"
    P(hdr)
    for lab in ["actual"] + [d[0] for d in DT]:
        a = np.array(res[lab]); s = [a.sum()] + [a[bots == b].sum() for b in ("FRESH", "MINUTE", "OLD")]
        top = np.sort(a)[::-1][: max(1, len(a) // 20)].sum()
        P(f"  {lab:26} " + " ".join(f"{x:+9.3f}" for x in s) + f"  {100*np.mean(a>0):4.0f}  {100*top/a.sum() if a.sum()>0 else float('nan'):5.0f}%")
    if D == "D1":
        a = np.array(res["actual"]); b = np.array(res["2 slots(=our 200ms+land)"]); lots = res["_lot"]
        d = a - b; idx = np.argsort(d)
        P("  examples: lots where his longer hold made the most vs our 2-slot exit (actual, 2-slot):")
        for k in idx[::-1][:6]:
            l = LL[lots[k]]; P(f"    {l['bot']:6} hold {l['hold_s']:5}s actual {a[k]:+.3f} vs 2-slot {b[k]:+.3f}  {l['gmgn']}  buy {l['buy_tx']}  sell {X.ss(l['sells'][0][0])}")
        P("  examples: lots where his hold lost the most vs our 2-slot exit:")
        for k in idx[:6]:
            l = LL[lots[k]]; P(f"    {l['bot']:6} hold {l['hold_s']:5}s actual {a[k]:+.3f} vs 2-slot {b[k]:+.3f}  {l['gmgn']}  buy {l['buy_tx']}  sell {X.ss(l['sells'][0][0])}")
open(f"{X.X}/x8.txt", "w").write("\n".join(out) + "\n")
