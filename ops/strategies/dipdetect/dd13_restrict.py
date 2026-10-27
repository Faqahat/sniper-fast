#!/usr/bin/env python3
# Deployment-oriented restrictions of NEW-A (v3_reg4_nof1 >= 0.0041, exit 0.85 s): only inside the current envelope, or inside a
# widened envelope (age <= 343.67 s, drop >= 4.65%, sell >= 0.5 SOL, any time since the last buy). Engine replay, FRA+AMS.
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
P = np.load(f"{L.OUT}/pred_v3_reg4_nof1.npy"); o = 0; PP = {}
for day in DAYS:
    n = len(L.load(day)["k"]); PP[day] = P[o:o + n]; o += n
E = L.EXI["c4_tpnone_slnone"]
for nm, mk in (("NEW-A all dumps", lambda d, p: p >= 0.0041),
               ("NEW-A inside current envelope", lambda d, p: (p >= 0.0041) & d["env"]),
               ("NEW-A inside widened envelope", lambda d, p: (p >= 0.0041) & (L.feat(d, "age_s") <= 343.67) & (L.feat(d, "drop_pct") >= 4.65) & (L.feat(d, "sol") >= 0.5)),
               ("NEW-A strict 0.010 inside current envelope", lambda d, p: (p >= 0.010) & d["env"]),
               ("BASE IMIT1 top4 (exit 0.85 s no TP)", lambda d, p: np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]))):
    print(f"\n### {nm}")
    for day in DAYS[1:]:
        d = L.load(day); h = L.hours(d); sel = mk(d, PP[day])
        cells = []
        for latx, lat in enumerate((35, 50, 75)):
            r = L.sim(d, sel, latx, E)
            cells.append(f"{lat}ms {r['pnl']:+6.2f} ({r['pnl'] / h * 24:+6.2f}/24h) {r['fill']:4d}/{r['att']:4d} {r['per_fill']:+.4f}/fill")
        print(f"  {day}: " + " | ".join(cells))
