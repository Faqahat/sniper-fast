#!/usr/bin/env python3
# SAME-SLOT COPY + SHORT HOLD (read-only, reuses a3_copy.replay): we buy right behind their first buy IN THEIR SLOT
# (T0 = the very next tx after theirs; SLOT_END = after every trade of their slot), plus 35 / 75 ms for reference, then sell on a
# timer: 0.5, 1, 2, 3, 5, 10, 20 s after our fill (the sell lands at that time). 1 SOL. Costs: pump fee both sides (in the replay) + 0.0015 SOL per tx x2.
# Follower variants: all (keep every follower), slip (drop followers whose decoded slippage limit fails at the replayed price), drop2 (drop all outside buys within 2 slots after us).
import os, sys, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import a3_copy as A, lib3
from multiprocessing import Pool
HOLDS = [0.5, 1, 2, 3]; TX = 0.0015; B = 1.0
def work(pi):
    p = A.P[pi]; tr = A.T_[p["m"]]; W = lib3.W3[p["w"]]; c = A.L[p["m"]]; k0 = p["k0"]; out = []
    m0 = A.msf(tr[k0]); slot_end = (tr[k0]["s"] + 1) * 212.0 - 0.001 - m0
    for tname, T in (("T0", 0.0), ("5ms", 5.0), ("10ms", 10.0), ("15ms", 15.0), ("20ms", 20.0), ("25ms", 25.0), ("35ms", 35.0)):
        for var in ("all", "slip"):
            R = A.replay(tr, k0, W, T, B, var, c)
            if R is None: continue
            res = {}
            for h in HOLDS:
                j = A.exit_at(R, R["fill_ms"] + h * 1000)
                res[h] = R["v"][j] * B - B - 2 * TX
            out.append(dict(w=p["w"], run=p["run"], T=tname, var=var, pnl=res, over=R["entry_vs_them"] - 1, same=(R["ms"][0] // 212) == (m0 // 212)))
    return out
if __name__ == "__main__":
    A.init()
    rows = []
    with Pool(8, initializer=A.init) as pool:
        for o in pool.imap_unordered(work, range(len(A.P)), chunksize=4): rows += o
    json.dump(rows, open("out/speed_sweep.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    HRS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}
    med = lambda v: statistics.median(v) if v else float("nan")
    for var in ("all", "slip"):
        print(f"\n######## follower variant: {var}  (1 SOL per copy; SOL totals over 60.7 h; per run R2 / R3 / R1)")
        for wset, ws in (("ALL", ("Fsb6Ns75", "pXGQ6J2z", "4vw54BmA")), ("Fsb6Ns75", ("Fsb6Ns75",)), ("pXGQ6J2z", ("pXGQ6J2z",)), ("4vw54BmA", ("4vw54BmA",))):
            print(f"  --- {wset}")
            for tname in ("T0", "5ms", "10ms", "15ms", "20ms", "25ms", "35ms"):
                v = [r for r in rows if r["var"] == var and r["T"] == tname and r["w"] in ws]
                if not v: continue
                cells = []
                for h in HOLDS:
                    x = [r["pnl"][h] for r in v]; byrun = {run: sum(r["pnl"][h] for r in v if r["run"] == run) for run in ("R2", "R3", "R1")}
                    cells.append(f"{h:>3}s {sum(x):+6.1f} ({sum(1 for y in x if y > 0) / len(x):3.0%} up; {byrun['R2']:+.1f}/{byrun['R3']:+.1f}/{byrun['R1']:+.1f})")
                print(f"    {tname:8s} n={len(v):3d} pay +{med([r['over'] for r in v]):4.0%} vs them | " + " | ".join(cells))
