#!/usr/bin/env python3
"""EXPLORATION: single-feature ARM skip rules, scored on (a) the chain-wide tuning events (proxy, INFERRED; validation period excluded)
and (b) the dev live windows (MEASURED, sim.py). Validation is NOT read here. Every (feature, direction, threshold) is a config."""
import json, sys
import numpy as np
import sim
B = "/home/moiz/sniper-data/presend_filter"
T_VAL0, T_VAL1 = 1792948200, 1793033220
E = [e for e in json.load(open(f"{B}/chain_events.json")) if not (T_VAL0 <= e["bt"] < T_VAL1)]
UNF = 0.000164          # dev: mean failed-try fees of an armed window that did not fill (MEASURED)
FILLFEE = 0.000075      # dev: mean failed-try fees of a window that filled
ev_val = np.array([(e["y_net"] - FILLFEE) if e["fill"] else -UNF for e in E])
DEV = ("ams:r24", "ams:r25")
W = sim.load(DEV)
feats = sys.argv[1:] or ["age", "n_tr", "n_users", "vol", "n_tr_10", "n_tr_50", "n_u_10", "cre_prev", "dev_hold", "wh_nf", "wh_bounce", "wh_dump_fol", "wh_n",
                         "wh_tokens_before", "coh_n", "coh_hold", "fb_n", "fb_hold", "fb_n20", "n_big", "top10", "pct", "whale_sol", "vsol", "tok_dumps",
                         "tok_dump_fol", "since_last", "p_ret_20", "dd_peak", "trig_tip"]
rows = []
n = 0
for f in feats:
    x = np.array([float(e.get(f)) if e.get(f) is not None else np.nan for e in E])
    for q in (5, 10, 15, 20, 30):
        for side in ("low", "high"):
            thr = float(np.nanpercentile(x, q if side == "low" else 100 - q))
            sk = (x < thr) if side == "low" else (x > thr)
            if sk.sum() < 100: continue
            n += 1
            g_chain = -ev_val[sk].sum()
            arm = (lambda w, f=f, thr=thr, side=side: not ((w.get(f) is not None) and ((w[f] < thr) if side == "low" else (w[f] > thr))))
            r = sim.evaluate(W, arm=arm)
            rows.append((g_chain, f, side, thr, int(sk.sum()), r["ALL"]["gain"], r["ams:r24"]["gain"], r["ams:r25"]["gain"], int(r["ALL"].get("win_rm", 0)),
                         r["ALL"].get("win_rm_sol", 0), int(r["ALL"].get("lose_rm", 0)), r["ALL"].get("lose_rm_sol", 0), int(r["ALL"].get("notrade_rm", 0))))
rows.sort(key=lambda r: -r[0])
print(f"configs: {n}\n{'chain gain':>10s} {'feature':16s} side  thr        n_chain | dev gain (r24, r25) | win_rm (SOL) lose_rm (SOL) notrade_rm")
for r in rows[:45]:
    print(f"{r[0]:+10.3f} {r[1]:16s} {r[2]:5s} {r[3]:<10.4g} {r[4]:5d} | {r[5]:+.3f} ({r[6]:+.3f}, {r[7]:+.3f}) | {r[8]:3d} ({r[9]:+.3f}) {r[10]:3d} ({r[11]:+.3f}) {r[12]}")
