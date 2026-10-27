#!/usr/bin/env python3
# Which study dumps can the ENGINE score? (agent 10-25) The live engine evaluates a dump only when its IMIT1 token book emits a
# dump EVENT (dip_imit.rs TokenBook::push): a real sell >= 1 SOL, curve < 100 SOL after it, age >= 1 s, and the FIRST such sell
# of its slot on that token (later big sells of the same slot are never events). The study's Stage A replay uses every dump.
# This marks each dd1 row "visible" (first qualifying big sell of its slot) and replays Stage A (top25 >= thr, envelope, c4)
# with and without the visibility condition, 35 / 50 / 75 ms, FRA + AMS.   usage: python3 dd16_visible.py
import json
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
DAYDIR = {"R1": "/home/moiz/sniper-data/strategies/patterns", "R2": "/home/moiz/sniper-data/strategies/patterns",
          "R3": "/home/moiz/sniper-data/strategies/patterns", "R4": L.OUT}
E4 = L.EXI["c4_tpnone_slnone"]

def visible(day, d):
    z = np.load(f"{DAYDIR[day]}/day_{day}.npz"); s = z["s"]; buy = z["buy"]; sol = z["sol"]; vsol = z["vsol"]; tok = z["tok"]
    # previous qualifying big sell of the same token in the same slot, for every trade (chain order inside each token)
    big = (buy == 0) & (sol >= 1e9) & (vsol < 100e9)
    vis = np.ones(len(d["k"]), bool)
    k = d["k"]
    for r, g in enumerate(k.tolist()):
        j = g - 1
        while j >= 0 and tok[j] == tok[g] and s[j] == s[g]:
            if big[j]: vis[r] = False; break
            j -= 1
    return vis

if __name__ == "__main__":
    P = np.load(f"{L.OUT}/pred_v3_reg4_top25.npy"); thr = json.load(open(f"{L.OUT}/dd15_stageA.json"))["thr_top25"]
    D = {}; o = 0; PP = {}
    for day in DAYS:
        D[day] = L.load(day); n = len(D[day]["k"]); PP[day] = P[o:o + n]; o += n
    cut = np.quantile(D["R2"]["t"], 0.70)
    out = {}
    for day in DAYS:
        d = D[day]; w = (d["t"] >= cut) if day == "R2" else np.ones(len(d["t"]), bool)
        vis = visible(day, d)
        a = (PP[day] >= thr) & d["env"] & w
        base = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]) & w
        print(f"{day}{'val' if day == 'R2' else ''}: in-envelope dumps {int((d['env'] & w).sum())}, not visible to the engine {int((d['env'] & w & ~vis).sum())}; "
              f"Stage A picks {int(a.sum())}, not visible {int((a & ~vis).sum())}; IMIT1 top4 rows not visible {int((base & ~vis).sum())}", flush=True)
        for nm, sel in (("Stage A (all dumps)", a), ("Stage A (engine-visible only)", a & vis)):
            cells = []
            for li, lat in enumerate((35, 50, 75)):
                r = L.sim(d, sel, li, E4); out[f"{nm}|{day}|{lat}"] = r["pnl"]
                cells.append(f"{lat}ms {r['pnl']:+6.2f} ({r['fill']}/{r['att']})")
            print(f"   {nm:32s} " + " | ".join(cells), flush=True)
    for nm in ("Stage A (all dumps)", "Stage A (engine-visible only)"):
        print(f"pooled {nm:32s} R3+R4 " + " / ".join(f"{sum(out[f'{nm}|{dd}|{lat}'] for dd in ('R3', 'R4')):+.2f}" for lat in (35, 50, 75)) +
              " | R3+R1+R4 " + " / ".join(f"{sum(out[f'{nm}|{dd}|{lat}'] for dd in ('R3', 'R1', 'R4')):+.2f}" for lat in (35, 50, 75)))
    json.dump(out, open(f"{L.OUT}/dd16_visible.json", "w"))
