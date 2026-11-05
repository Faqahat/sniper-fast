#!/usr/bin/env python3
"""e4: exit timer change as a SHIFT of the real decision time (keeps the engine's own timer overshoot): decide at real T + s ms
(s = new timer - 200), never before our fill is seen. Only "time-ms" exits. Own landing delay L. Per period, VAL w/o the 11-02 attack
span, per run, per 12 h block, and w/o the 5 best changes."""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
HRS = {"DEV": 74.35, "VAL": 20.61}
ATT = (1793590104000000000, 1793590615000000000)  # 11-02 08:28:24 .. 08:36:55 PKT (tune.json ATTACK)
SH = (-150, -100, -75, -50, -25, 25, 50, 100)
R = collections.defaultdict(lambda: collections.defaultdict(list))
for d in tlib.load():
    p = tlib.Pos(d)
    if not p.ok or p.why != "time-ms": continue
    per = d["per"]; att = ATT[0] <= d["t"] <= ATT[1]
    blk = "B%02d" % ((d["t"] - 1793241000000000000) // (12 * 3600 * 10**9))
    for s in SH:
        T = max(p.T + s * 1e6, p.tfill + 1e6)
        if T + p.L > p.tape_end_t(): T = p.tape_end_t() - p.L
        cf, _ = p.proceeds_at(T)
        dd = (cf - p.act) * (1 - tlib.FEE_SELL) / 1e9
        for k in (per, per + ("_att" if att else "_noatt"), d["run"] + "/" + per, blk):
            R[k][s].append((dd, d["pnl"]))
def line(k, hrs=None):
    out = []
    for s in SH:
        v = R[k][s]; tot = sum(x[0] for x in v); w5 = sum(sorted((x[0] for x in v), reverse=True)[5:])
        win_b = sum(x[1] > 0 for x in v) / max(len(v), 1); win_a = sum(x[1] + x[0] > 0 for x in v) / max(len(v), 1)
        out.append(f"{200+s}ms {tot:+.3f}" + (f" ({tot/hrs*24:+.2f}/d)" if hrs else "") + f" w/o5 {w5:+.2f} win {win_b:.2f}>{win_a:.2f}")
    print(f"{k:12s} n {len(R[k][SH[0]]):4d} | " + " | ".join(out))
for k in ("DEV", "VAL", "VAL_noatt", "VAL_att"): line(k, HRS.get(k))
for k in sorted(x for x in R if "/" in x): line(k)
for k in sorted(x for x in R if x.startswith("B")): line(k)
