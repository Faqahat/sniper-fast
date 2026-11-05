#!/usr/bin/env python3
"""e2: what our SELL latency costs. Same decision time, landing delay L replaced by 0 / 25 / 50 ms / half of ours (tlib replay).
Also: P&L by our measured decision->landing delay bucket (real money)."""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
HRS = {"DEV": 74.35, "VAL": 20.61}
res = collections.defaultdict(lambda: collections.defaultdict(float)); cnt = collections.Counter()
byL = collections.defaultdict(lambda: [0, 0.0, 0])
for d in tlib.load():
    p = tlib.Pos(d)
    if not p.ok: continue
    per = d["per"]; cnt[per] += 1
    for lab, L in (("L=0", 0), ("L=25ms", 25e6), ("L=50ms", 50e6), ("L/2", p.L / 2), ("L=min(L,60ms)", min(p.L, 60e6))):
        cf, _ = p.proceeds_at(p.T, L)
        res[per][lab] += (cf - p.act) * (1 - tlib.FEE_SELL) / 1e9
    Lm = p.L / 1e6
    b = "<=30" if Lm <= 30 else "<=60" if Lm <= 60 else "<=100" if Lm <= 100 else "<=200" if Lm <= 200 else ">200"
    x = byL[(per, b)]; x[0] += 1; x[1] += d["pnl"]; x[2] += d["pnl"] > 0
for per in ("DEV", "VAL"):
    print(per, "positions", cnt[per], {k: f"{v:+.3f} SOL ({v/HRS[per]*24:+.2f}/day)" for k, v in res[per].items()})
print("real P&L by our sell's decision->landing delay (ms):")
for k in sorted(byL): print("  ", k, byL[k][0], f"{byL[k][1]:+.3f}", f"{1000*byL[k][1]/byL[k][0]:+.1f} mSOL", f"win {byL[k][2]/byL[k][0]:.2f}")
