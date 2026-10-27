#!/usr/bin/env python3
# Exit scan for a selection (baseline IMIT1 top4, or a trained detector at its threshold): every exit of the dd1 grid (time limit
# 2-38 slots x TP x SL) through the engine replay (hold time changes the busy window), FRA+AMS. The exit is CHOSEN on R2 (sum of
# 35 + 50 ms) and then shown on R3 / R1 / R4; the two live exits are shown alongside.
# usage: python3 dd9_exits.py base            |  python3 dd9_exits.py <pred name> <threshold>
import sys
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
def preds(name):
    P = np.load(f"{L.OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(L.load(day)["k"]); out[day] = P[o:o + n]; o += n
    return out
if __name__ == "__main__":
    D = {day: L.load(day) for day in DAYS}
    if sys.argv[1] == "base":
        S = {day: np.isfinite(D[day]["f1"]) & (D[day]["f1"] >= L.THR["top4"]) for day in DAYS}; tag = "baseline IMIT1 top4"
    else:
        P = preds(sys.argv[1]); thr = float(sys.argv[2]); S = {day: P[day] >= thr for day in DAYS}; tag = f"{sys.argv[1]} >= {thr}"
        cut = np.quantile(D["R2"]["t"], 0.70); S["R2"] = S["R2"] & (D["R2"]["t"] >= cut)      # R2: validation slice only
    res = {}
    for e, en in enumerate(L.EXN):
        res[en] = {(day, lat): L.sim(D[day], S[day], lat, e)["pnl"] for day in DAYS for lat in (0, 1)}
    rank = sorted(L.EXN, key=lambda en: -(res[en][("R2", 0)] + res[en][("R2", 1)]))
    print(f"exit scan for {tag} (FRA+AMS, SOL): R2(35/50) | R3 | R1 | R4")
    def line(en, mark=""):
        print(f"  {mark}{en:20s} " + " | ".join(f"{res[en][(day, 0)]:+6.2f}/{res[en][(day, 1)]:+6.2f}" for day in DAYS))
    for en in rank[:12]: line(en)
    print("  live exits:"); line("c6_tpnone_sl10", "*"); line("c19_tpnone_sl20", "*")
    print("  best on each TEST day (for reference only, not a choice):")
    for day in DAYS[1:]:
        b = max(L.EXN, key=lambda en: res[en][(day, 0)] + res[en][(day, 1)]); line(b, f"{day} ")
