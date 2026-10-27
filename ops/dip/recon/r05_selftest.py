#!/usr/bin/env python3
# r05: self-test: rsim.run_path with our trades KEPT reproduces dd1_build.path() row by row (same tape, 35/50/75 ms, 3 exits)
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
tag = sys.argv[1] if len(sys.argv) > 1 else "NEW"
TP = S.Tapes(tag)
z0 = np.load(f"{R.WORK}/{tag}/dd1_{tag}.npz"); z = {k: z0[k] for k in ("k", "tok", "st", "pnl")}; meta = json.load(open(f"{R.WORK}/{tag}/dd1_meta.json"))
EXN = meta["exits"]; EXI = {k: i for i, k in enumerate(EXN)}
rng = np.random.default_rng(1); rows = rng.choice(len(z["k"]), 3000, replace=False)
bad = 0; nst = 0; npn = 0; maxd = 0
for r in rows:
    k = int(z["k"][r]); t = int(z["tok"][r]); tp = TP.token(t); j0 = k - tp["o"]
    for li, L in enumerate((35, 50, 75)):
        res = S.run_path(tp, j0, 0.55, L=L, drop_ours=False)
        st = int(z["st"][r, li]); nst += 1
        if res["st"] != st: bad += 1; continue
        if st != 0: continue
        for ex, (cap, sl) in (("c6_tpnone_sl10", (6, 0.10)), ("c4_tpnone_slnone", (4, None)), ("c19_tpnone_sl20", (19, 0.20))):
            v, _, _ = S.exits(res, cap, sl=sl)
            d = abs((v - 0.55) - float(z["pnl"][r, li, EXI[ex]])); maxd = max(maxd, d); npn += 1
            if d > 1e-5: bad += 1
print(f"{tag}: status checks {nst}, P&L checks {npn}, mismatches {bad}, max |diff| {maxd:.2e} SOL")
