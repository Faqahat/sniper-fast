#!/usr/bin/env python3
"""SELECT step 1b (read-only): per envelope sell, the FOLLOW it got = outside buy SOL (haqq and our wallets excluded) landing after it within
slots s..s+2 (fol2) and the count (nb2). MEASURED. Then identity MEMORY features (causal: only earlier sells whose 2-slot window closed,
slot <= s-3, on OTHER mints):
  f_sel_mfol  : the seller's mean fol2 on earlier envelope sells (other mints), -1 if none
  f_sel_nfol  : how many such sells
  f_cr_mfol   : mean fol2 over earlier envelope sells on the CREATOR's other tokens, -1 if none
Appends to env.npz (rewritten). These do not use haqq at all (we could compute them live)."""
import sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"


def main():
    t0 = time.time()
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in Z.files}; del Z
    ids, idm = L.ids_map(); excl = [idm[L.HAQQ]] + [idm[w] for w in L.WAL.values() if w in idm]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mm = np.asarray(T["mint"]); ms = np.unique(A["m"]).astype(np.uint32)
    sel = np.flatnonzero(np.isin(mm, ms)); del mm
    m_ = np.asarray(T["mint"])[sel].astype(np.int64); s_ = np.asarray(T["slot"])[sel].astype(np.int64); i_ = np.asarray(T["idx"])[sel].astype(np.int64)
    b_ = np.asarray(T["buy"])[sel].astype(bool); u_ = np.asarray(T["user"])[sel].astype(np.int64); so = np.asarray(T["sol"])[sel] / 1e9
    o = np.lexsort((i_, s_, m_)); m_, s_, i_, b_, u_, so = m_[o], s_[o], i_[o], b_[o], u_[o], so[o]
    ob = b_ & ~np.isin(u_, excl)
    S0 = int(s_.min())
    key = m_ * 10**12 + (s_ - S0) * 10**5 + i_
    cb = np.concatenate([[0], np.cumsum(np.where(ob, so, 0.0))]); cn = np.concatenate([[0], np.cumsum(ob)])
    em = A["m"].astype(np.int64); es = A["s"].astype(np.int64); ei = A["i"].astype(np.int64)
    a = np.searchsorted(key, em * 10**12 + (es - S0) * 10**5 + ei, side="right")
    b = np.searchsorted(key, em * 10**12 + (es + 3 - S0) * 10**5)
    fol2 = cb[b] - cb[a]; nb2 = cn[b] - cn[a]
    A["fol2"] = fol2.astype(np.float32); A["nb2"] = nb2.astype(np.int32)
    print(f"fol2 done: mean {fol2.mean():.3f} SOL; y1 {fol2[A['y247'] | A['y248']].mean():.3f} vs not {fol2[~(A['y247'] | A['y248'])].mean():.3f} ({time.time() - t0:.0f}s)", flush=True)
    # memory per seller (other mints), window closed (slot <= s-3)
    for gk, nm in (("sel", "sel"), ("cr", "cr")):
        g = A[gk].astype(np.int64)
        o = np.lexsort((ei, es, g)); kg = g[o] * 10**8 + (es[o] - S0); cf = np.concatenate([[0], np.cumsum(fol2[o])])
        q0 = np.searchsorted(kg, g * 10**8); q3 = np.searchsorted(kg, g * 10**8 + (es - 2 - S0))
        n_all = q3 - q0; f_all = cf[q3] - cf[q0]
        # same-mint part (exclude): pair id (group, mint)
        _, pid = np.unique(g * 10**6 + em, return_inverse=True); pid = pid.astype(np.int64)
        o2 = np.lexsort((ei, es, pid)); k2 = pid[o2] * 10**8 + (es[o2] - S0); cf2 = np.concatenate([[0], np.cumsum(fol2[o2])])
        r0 = np.searchsorted(k2, pid * 10**8); r3 = np.searchsorted(k2, pid * 10**8 + (es - 2 - S0))
        n = n_all - (r3 - r0); f = f_all - (cf2[r3] - cf2[r0])
        n = np.where(g >= 0, n, 0)
        A[f"f_{nm}_mfol"] = np.where(n > 0, f / np.maximum(n, 1), -1).astype(np.float32); A[f"f_{nm}_nfol"] = n.astype(np.float32)
        print(f"{nm} memory: share with history {np.mean(n > 0):.3f} ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{OUT}/env.tmp.npz", **A)
    import os; os.replace(f"{OUT}/env.tmp.npz", f"{OUT}/env.npz")
    print(f"saved ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
