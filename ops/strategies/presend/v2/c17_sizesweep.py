#!/usr/bin/env python3
# PRE-SEND V2 step c17 (owner 10-25): SIZE SWEEP 0.35 / 0.55 / 0.75 / 1.0 SOL for
#   A6 = whale >= 6%, 4/slot;  B6 = whale >= 6%, 8/slot;  B5 = whale >= 5%, 8/slot   (T2, W 10, y 12%, exit c2_tp10_sl20, 1 server, real costs)
# Per config x size: TEST (R3 + R4) SOL/day with the 90% clock-hour bootstrap, fills/day, net per fill, worst clock hour, worst single
# fill; the pessimistic-landing row; the FRESH hours R5 (built after every choice; per clock hour); and the size effect split:
#   model  = the normal replay (followers whose slippage our buy breaks are dropped: generic slack table, INFERRED);
#   naive  = PSV2_NAIVE=1 replay (every later buy happens as recorded): what is left is our own buy's price impact on the real tape.
# -> presend_v2/c17_sizesweep.json + .txt
import os, sys, json, importlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
OUT = f"{V.OUT}/c17_sizesweep"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
rng = np.random.default_rng(11)
SIZES = (0.35, 0.55, 0.75, 1.0)
CFG = {"A6 (whale>=6%, 4/slot)": (6.0, "L4", "L4x"), "B6 (whale>=6%, 8/slot)": (6.0, "L8", "L8x"), "B5 (whale>=5%, 8/slot)": (5.0, "L8", "L8x")}
DAYS = ("R3", "R4", "R5")

def load(tag):
    os.environ["PSV2_TAG"] = tag
    import v2eng as E; importlib.reload(E)
    import v2run as R; importlib.reload(R)
    R.G["DD"] = {d: E.load(d) for d in DAYS}
    return E, R

E, R = load("")
DD = R.G["DD"]
En, Rn = load("_naive")
DDn = Rn.G["DD"]
os.environ["PSV2_TAG"] = ""
H = {d: DD[d]["hours"] for d in DAYS}
say(f"SIZE SWEEP | TEST = R3 + R4 ({H['R3'] + H['R4']:.1f} h) | FRESH R5 = {V.WIN['R5'][0]} -> {V.WIN['R5'][1]} PKT ({H['R5']:.2f} h) | 1 server, real costs")
res = {}
for name, (hmin, row, rowx) in CFG.items():
    say(f"\n=== {name}")
    for sz in SIZES:
        cfg = dict(spec=dict(fam="T2", hmin=hmin), W=10, y=0.12, row=row, size=sz, ex="c2_tp10_sl20", lead="all", servers=1, cost="real")
        R.G["DD"] = DD
        r = R.ev(cfg, DAYS, detail=True)
        te_p = r["R3"]["pnl"] + r["R4"]["pnl"]; te_h = H["R3"] + H["R4"]; te_f = r["R3"]["fill"] + r["R4"]["fill"]
        hours = np.concatenate([E.hourly(r[d], d) for d in ("R3", "R4")])
        boot = hours[rng.integers(0, len(hours), (4000, len(hours)))].sum(1) / te_h * 24
        nets = np.concatenate([r[d]["acc_net"] for d in ("R3", "R4")])
        gross = (r["R3"]["gross"] + r["R4"]["gross"]) / max(te_f, 1)
        worst_h = float(hours.min())
        r5 = r["R5"]; r5h = E.hourly(r5, "R5")
        cx = dict(cfg, row=rowx)
        rx = R.ev(cx, ("R3", "R4", "R5"))
        pess = (rx["R3"]["pnl"] + rx["R4"]["pnl"]) / te_h * 24
        Rn.G["DD"] = DDn
        rn = Rn.ev(cfg, ("R3", "R4", "R5"))
        naive24 = (rn["R3"]["pnl"] + rn["R4"]["pnl"]) / te_h * 24
        naive_gross = (rn["R3"]["gross"] + rn["R4"]["gross"]) / max(rn["R3"]["fill"] + rn["R4"]["fill"], 1)
        o = dict(test24=te_p / te_h * 24, ci=[float(np.percentile(boot, 5)), float(np.percentile(boot, 95))], fills24=te_f / te_h * 24,
                 per_fill=te_p / max(te_f, 1), margin=gross / sz, worst_hour=worst_h, worst_fill=float(nets.min()) if len(nets) else 0.0,
                 p1_fill=float(np.percentile(nets, 1)) if len(nets) else 0.0, pess24=pess, pess_r5=rx["R5"]["pnl"],
                 r5=dict(pnl=r5["pnl"], per24=r5["per24"], fills=r5["fill"], per_fill=r5["per_fill"], hourly=[float(x) for x in r5h],
                         worst_fill=float(r5["acc_net"].min()) if r5["fill"] else 0.0),
                 naive24=naive24, naive_margin=naive_gross / sz, naive_r5=rn["R5"]["pnl"],
                 days={d: r[d]["per24"] for d in ("R3", "R4")})
        res[f"{name}|{sz}"] = o
        say(f"  {sz:4.2f} SOL: TEST {o['test24']:+6.2f}/d [{o['ci'][0]:+.2f}, {o['ci'][1]:+.2f}] (R3 {o['days']['R3']:+.2f}, R4 {o['days']['R4']:+.2f}) | pess {pess:+6.2f}/d | "
            f"{o['fills24']:4.0f} fills/d, net {o['per_fill']:+.4f}/fill, margin after pump fees {100 * o['margin']:.2f}% | worst hour {worst_h:+.3f}, "
            f"worst fill {o['worst_fill']:+.3f} (p1 {o['p1_fill']:+.3f}) | naive (no crowd-out) {naive24:+6.2f}/d, margin {100 * o['naive_margin']:.2f}%")
        say(f"        FRESH R5: {r5['pnl']:+.3f} SOL ({r5['per24']:+.2f}/24h), {r5['fill']} fills, net {r5['per_fill']:+.4f}/fill, worst fill {o['r5']['worst_fill']:+.3f} | "
            f"pess {rx['R5']['pnl']:+.3f} | naive {rn['R5']['pnl']:+.3f} | hours " + " ".join(f"{x:+.2f}" for x in r5h))
json.dump(res, open(OUT + ".json", "w"), default=float, indent=1)
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
