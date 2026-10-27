#!/usr/bin/env python3
"""DV8 step 3a check (read-only): recompute 400 random filled (candidate, landing model, exit, fol) outcomes of uni.npz with the
scalar dv8sim.pnl_exact on the mint's own rows -> max abs difference. Also: share of candidates whose exit had no later trade."""
import sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
Z = np.load(f"{L.D}/uni.npz"); M = Z["M"]; R = Z["R"]; ES = Z["ES"]; PN = Z["PN"]; FILL = Z["FILL"]; HS = list(Z["HS"]); FOLS = list(Z["FOLS"])
ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values()]
T = np.load(f"{L.TAB}/trades.npy"); T = T[~np.isin(T["user"], our)]; T = T[np.argsort(T["mint"], kind="stable")]
sl = T["slot"].astype(np.int64); vs = T["vsol"] / 1e9; vt = T["vtok"].astype(np.float64); so = T["sol"] / 1e9; tk = T["tok"].astype(np.float64); bu = T["buy"].astype(bool)
g = np.random.default_rng(0); err = []
ci, mj = np.nonzero(FILL)
for k in g.integers(0, len(ci), 400):
    c, m = ci[k], mj[k]; hi = g.integers(0, len(HS)); fi = g.integers(0, len(FOLS))
    if not np.isfinite(PN[c, m, hi, fi]): continue
    r = R[c, m]; end = M["end"][c]; tgt = ES[c, m] + HS[hi]
    q = r - 1
    while q + 1 < end and sl[q + 1] <= tgt: q += 1
    v = S.pnl_exact(vs, vt, so, tk, bu, r, q, 0.4, fol=FOLS[fi])
    err.append(abs(v - PN[c, m, hi, fi]))
print(f"checked {len(err)}: max abs diff {max(err):.2e} SOL, mean {np.mean(err):.2e}")
