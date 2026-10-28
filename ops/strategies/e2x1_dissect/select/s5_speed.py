#!/usr/bin/env python3
"""SELECT s5: entry speed. For each E2x1 buy: the trigger = biggest |price impact| outside trade in slots [s-3, s] before his row
(ties -> latest), plus the plain previous trade. Lag in slots, in block index and in chain-clock ms (slot*212 + idx/blocksize*212,
blocksize = max idx seen in the recorder + 1). Also: what his lot would have returned entering 1 or 2 slots later
(entry px = px after the last row of slot s+1 / s+2, exit = his realised avg sell px on the mint; MEASURED tape prices,
INFERRED fill = no own impact)."""
import sys, pickle, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"])
S = np.load(f"{TP}/slots.npy"); s0 = int(S["slot"].min())
bsz = np.full(int(S["slot"].max()) - s0 + 1, 400.0); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.float64) + 1
def cc(s, i): return s * SMS + i / max(bsz[s - s0], i + 1.0) * SMS
X = pickle.load(open(f"{OUT}/buys.pkl", "rb"))
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); us = D["user"]; bu = D["buy"].astype(bool)
lp = np.log(D["vsol"] / np.maximum(D["vtok"].astype(np.float64), 1)); tk = D["tok"].astype(np.float64); so = D["sol"] / 1e9
res = []
for f in X:
    R = f["row"]; m = f["mint"]; a, e = span(D, m); s = int(sl[R])
    lo = a + int(np.searchsorted(sl[a:R], s - 3))
    best = None
    for q in range(lo, R):
        if us[q] == w or q == a: continue
        im = np.exp(lp[q] - lp[q - 1]) - 1
        if best is None or abs(im) >= abs(best[1]): best = (q, im)
    q = R - 1
    g = dict(row=R, lag_prev_sl=int(s - sl[q]), lag_prev_ms=cc(s, ix[R]) - cc(int(sl[q]), ix[q]), his_idx=int(ix[R]), his_frac=ix[R] / bsz[s - s0])
    if best:
        q, im = best
        g.update(trg_imp=float(im), trg_buy=bool(bu[q]), trg_sol=float(so[q]), lag_trg_sl=int(s - sl[q]), lag_trg_ms=cc(s, ix[R]) - cc(int(sl[q]), ix[q]),
                 trg_idx=int(ix[q]))
    # later-entry what-if
    my = np.flatnonzero((us[a:e] == w) & ~bu[a:e]) + a
    ts = tk[my].sum(); ss = so[my].sum()
    pf = np.exp(lp[R])
    for k in (1, 2):
        qq = a + int(np.searchsorted(sl[a:e], s + k, side="right")) - 1
        g[f"px_ratio_{k}"] = float(np.exp(lp[qq]) / pf)          # entry price later / his fill price (post-trade px)
    g["ret"] = f["lot_pnl"] / f["sol"]
    res.append(g)
pickle.dump(res, open(f"{OUT}/speed.pkl", "wb"))
A = {k: np.array([r.get(k, np.nan) for r in res], dtype=float) for k in res[0] if k != "row"}
A["trg_imp"] = np.array([r.get("trg_imp", np.nan) for r in res]); A["lag_trg_sl"] = np.array([r.get("lag_trg_sl", np.nan) for r in res])
A["lag_trg_ms"] = np.array([r.get("lag_trg_ms", np.nan) for r in res]); A["trg_buy"] = np.array([r.get("trg_buy", np.nan) for r in res], float)
def pr(t, x): x = x[np.isfinite(x)]; print(f"{t:40s} n={len(x):5d} p10 {np.percentile(x,10):8.1f} p25 {np.percentile(x,25):8.1f} med {np.median(x):8.1f} p75 {np.percentile(x,75):8.1f} p90 {np.percentile(x,90):8.1f}")
pr("lag to previous trade, ms", A["lag_prev_ms"])
pr("his block position (frac*100)", A["his_frac"] * 100)
for nm, msk in (("dump trigger (sell imp<=-5%)", (A["trg_imp"] <= -0.05) & (A["trg_buy"] == 0)), ("pump trigger (buy imp>=+5%)", (A["trg_imp"] >= 0.05) & (A["trg_buy"] == 1)),
                ("small trigger (|imp|<5%)", np.abs(A["trg_imp"]) < 0.05)):
    print(f"== {nm}: n={msk.sum()} share {msk.mean():.2f}")
    pr("  lag slots", A["lag_trg_sl"][msk]); pr("  lag ms (chain clock)", A["lag_trg_ms"][msk])
    for k in (0, 1, 2, 3): print(f"    lag={k} slots: {np.mean(A['lag_trg_sl'][msk] == k):.2f}")
r = A["ret"]
for k in (1, 2):
    later = (1 + r) / A[f"px_ratio_{k}"] - 1
    print(f"entry +{k} slot: mean ret {100*np.mean(later):.2f}% vs his {100*np.mean(r):.2f}%; median px ratio {np.median(A[f'px_ratio_{k}']):.4f}; "
          f"pnl at his sizes {np.sum(later * np.array([x['sol'] for x in X])):.1f} vs {np.sum(r * np.array([x['sol'] for x in X])):.1f} SOL")
