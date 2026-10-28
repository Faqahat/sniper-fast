#!/usr/bin/env python3
"""LIM step 7 (read-only): replay haqq's own DIP fills with the exact curve model to split his edge into position vs exit.
For each DIP fill (data/lim/hctx2.pkl): tape rows of the mint with ALL his rows removed; his buy (actual spend) inserted at his
actual position; exits: timer h = 2/5/10/15/30 slots after his buy slot (last outside trade of that slot), fol 1.0 / 0.8.
Check: his measured FIFO lot P&L vs the replay - not exact (his other lots on the mint are removed), shown for scale.
Also flags the dumps we fired on (dv8 fires: same mint + dump slot/idx) and joins our counterfactual rows.
Out: data/lim/hrep.pkl"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
HS = [2, 5, 10, 15, 30]


def main():
    t0 = time.time()
    H = [r for r in pickle.load(open(f"{OUT}/hctx2.pkl", "rb")) if r["dip"] and r["ok"] and "lot_pnl" in r]
    ids, idm = L.ids_map(); hid = idm[L.HAQQ]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[r["mint"]] for r in H}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    FC = pickle.load(open(f"{OUT}/fires_cf.pkl", "rb"))
    fk = {}
    for f in pickle.load(open(f"{L.D}/fires_tape.pkl", "rb")):
        if f["ds"] is not None: fk[(f["mint"], f["ds"], f["di"])] = (f["run"], f["us"])
    by = collections.defaultdict(list)
    for r in H: by[r["mint"]].append(r)
    for mint, bl in by.items():
        a, b = span[mint]; R = TT[a:b]
        R = R[~((R["user"] == hid) | (R["signer"] == hid))]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        for r in bl:
            p = int(np.searchsorted(key, r["s"] * 100000 + r["i"]))
            r["rep"] = {}
            if p < 1: continue
            for h in HS:
                q = max(int(np.searchsorted(sl, r["s"] + h, side="right")) - 1, p - 1)
                for fo in (1.0, 0.8):
                    r["rep"][(h, fo)] = S.pnl_exact(vs, vt, sol, tk, bu, p, q, r["spend"], fol=fo)
            r["ours"] = fk.get((mint, r["d_slot"], r["d_idx"]))
    pickle.dump(H, open(f"{OUT}/hrep.pkl", "wb"))
    print("replayed", len(H), "on our fired dumps", sum(1 for r in H if r.get("ours")), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
