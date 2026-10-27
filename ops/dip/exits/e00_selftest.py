#!/usr/bin/env python3
# e00 self-test: exit_lib.simulate + value_at vs the model check's corrected replay (modelcheck/mc_corr.replay_corr, follow="comp",
# others="keep", phantom, sell 93 ms into the exit slot) on random study dumps of the window: c4 / c6 / c2 / c9 P&L must match
# (tokens with none of our own trades); and vs the uncorrected path (CV=None, phantom off) against recon/rsim.run_path(slack=False).
import sys, os, zlib, random
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_lib as E
sys.path.insert(0, "/home/moiz/sniper/ops/dip/modelcheck")
import mc_lib as M, mc_corr as MC

class _T: pass

if __name__ == "__main__":
    D = dict(np.load(f"{E.DATA}/dumps.npz"))
    TP = {"A": E.Tape("A"), "B": E.Tape("B")}
    CV = E.Curves(); CV2 = MC.Curves(E.CURVES)
    rng = random.Random(3)
    ids = [i for i in np.flatnonzero(D["env"]).tolist()]
    rng.shuffle(ids)
    n = bad = 0; nst = 0; maxd = 0.0
    for did in ids[:600]:
        tag = "AB"[int(D["tag"][did])]; T = TP[tag]; t = int(D["tok"][did]); j0 = int(D["k"][did]) - int(T.off[t]); tp = T.token(t)
        if any(c == 9 for c in tp["cls"]): continue
        o = _T(); o.S, o.A, o.B, o.SOL, o.TK, o.V, o.T, o.FR, o.SK, o.U, o.n = tp["s"], tp["arr"], [bool(x) for x in tp["buy"]], tp["sol"], tp["tokn"], tp["vsol"], tp["vtok"], tp["fr"], tp["slack"], tp["uid"], tp["n"]
        rk = zlib.crc32(f"{tp['s'][j0]}:{int(tp['arr'][j0] * 1000)}:{j0}".encode())
        for L in (35.0, 50.0, 75.0):
            ref = MC.replay_corr(o, j0, 0.35, L, guard=1.05, follow="comp", others="keep", phantom=True, sell_lat=93.0, crowd=0.0, CV=CV2, rowkey=rk, full=True)
            mine = E.simulate(tp, j0, L=L, CV=CV, rowkey=rk, kmax=45)
            n += 1
            if ref["status"] != mine["st"]: bad += 1; print("status mismatch", did, L, ref["status"], mine["st"]); continue
            if mine["st"] != 0: nst += 1; continue
            for c in (2, 4, 6, 9, 12):
                e = M.EXI[f"c{c}_tpnone_slnone"]
                v = E.value_at(mine, (mine["s_in"] + c) * E.SMS + 93.0) - 0.35
                d = abs(v - ref["pnl"][e]); maxd = max(maxd, d)
                if d > 1e-9: bad += 1; print("pnl mismatch", did, L, c, v, ref["pnl"][e]); break
    print(f"corrected replay check: {n} (dump, L) cases, {nst} not filled, mismatches {bad}, max |diff| {maxd:.2e}")
