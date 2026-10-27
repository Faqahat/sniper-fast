#!/usr/bin/env python3
# e12: stress test "+crowd" (model check: an extra early buyer crowds out ~40% of its SOL in later non-bot buys, INFERRED
# sensitivity). Same dumps, landings and models (trained WITHOUT the crowd-out); the paths are rebuilt with crowd = 0.4 and every exit
# is re-decided on what the feed would show in that world. TRAIN / TEST engine SOL/day, M2 / IMIT1, measured landing, + paired CI.
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e03_baselines as B, e_apply as AP, e05_report as R5

if __name__ == "__main__":
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(paths=f"{E.DATA}/paths/paths2_crowd.npz"); D = d.D
    P = {"TODAY_c4": d.tick_policy(np.full(len(d.s_in), 4)), "RUN10-14_c5_sl10": d.tpsl(5, sl=0.10), "cap2": d.tick_policy(np.full(len(d.s_in), 2)),
         "STALL1_k2_c30": B.stall_policy(d, 2, 1, 0.0, 30), "STALL2_k2_c30": B.stall_policy(d, 2, 2, 0.0, 30),
         "TREE_direct_d3": d.tick_policy(AP.apply_tree(d, f"{E.DATA}/e09_h1248_direct_d3.pkl")),
         "LEARN_h1248": d.tick_policy(AP.apply_saved(d, f"{E.DATA}/e04b_h1248_model.pkl")[0]),
         "LEARN_ENS3": d.tick_policy(AP.apply_saved(d, f"{E.DATA}/e04b_ENS3_model.pkl")[0])}
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    L("+CROWD STRESS (later non-bot buys shrink by 40% of our SOL): engine SOL/day, measured landing; TEST diff vs c4 with 90% CI (30-min blocks)")
    for w in ("M2", "IMIT1"):
        sel = d.picks(w); rows = {}
        for nm, (val, tdec, knd) in P.items():
            pnl = d.pnl(val, 0); r = {}
            for pn, per in PER.items():
                e = d.engine(sel, pnl, tdec, knd, lmode="meas", R=24, period=per, return_rows=(pn == "test"))
                r[pn] = V.fmt_day(e["pnl"], per)
                if pn == "test": rows[nm] = e["rows"]
            s = f"  {w:5s} {nm:18s} TRAIN {r['train']:+6.2f} | TEST {r['test']:+6.2f}"
            if nm != "TODAY_c4":
                bt = R5.block_sums(d, rows["TODAY_c4"], PER["test"], 24); bx = R5.block_sums(d, rows[nm], PER["test"], 24)
                df = bx - bt; lo, hi = R5.boot_ci(df); sc = 24 / V.hours(PER["test"])
                s += f"  diff {df.sum() * sc:+5.2f} [{lo * sc:+5.2f}, {hi * sc:+5.2f}]"
            L(s)
    open(f"{E.DATA}/e12_crowd.txt", "w").write("\n".join(lines) + "\n")
