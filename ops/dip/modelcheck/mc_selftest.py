#!/usr/bin/env python3
# self-test: mc_lib.replay (default mode) must reproduce the stored dd1 outputs (status, ratio, s_in, P&L of all 200 exits, exit offsets)
# on random dump rows of the given day, for dd1_<day>.npz (0.55 SOL, guard 1.05) and dd1_<day>_s0.35_g1000.npz (0.35, no guard).
import sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/modelcheck")
import mc_lib as M
day = sys.argv[1] if len(sys.argv) > 1 else "R4"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
d = M.load_day(day); rng = np.random.default_rng(1)
for fn, size, guard in ((f"dd1_{day}.npz", 0.55, 1.05), (f"dd1_{day}_s0.35_g1000.npz", 0.35, 1000.0)):
    z = np.load(f"{M.DDD}/{fn}"); k = z["k"]; st = z["st"]; ratio = z["ratio"]; sin = z["sin"]; pnl = z["pnl"]; off = z["off"]
    rows = rng.choice(len(k), size=min(N, len(k)), replace=False)
    bad = 0; maxd = 0.0; nfill = 0
    for r in rows:
        g = int(k[r]); t = int(d["tok"][g]); tp = M.Tape(d, t); j0 = g - tp.o
        for li, L in enumerate((35, 50, 75)):
            o = M.replay(tp, j0, size=size, L=L, guard=guard)
            if o["status"] != st[r, li] or abs(o["ratio"] - ratio[r, li]) > 1e-5 * ratio[r, li]: bad += 1; continue
            if o["status"] != 0: continue
            nfill += 1
            dv = np.abs(np.array(o["pnl"], np.float32) - pnl[r, li]).max(); maxd = max(maxd, float(dv))
            if o["s_in"] != sin[r, li] or dv > 1e-5 or (np.array(o["off"]) != off[r, li]).any(): bad += 1
    print(f"{fn}: rows {len(rows)} x 3 latencies, filled {nfill}, mismatches {bad}, max |pnl diff| {maxd:.2e}", flush=True)
