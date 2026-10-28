#!/usr/bin/env python3
"""SELECT s20: fat tail check. Per envelope (s9), share of moments whose token later GRADUATES (curve vSOL reaches >= 84 in the tape)
and whose price at any later point reaches 2x the moment's px: his picks vs skipped vs the GBDT's rate-matched TEST picks (MKT model)."""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load()
vs = D["vsol"] / 1e9; vt = D["vtok"].astype(np.float64); px = vs / np.maximum(vt, 1)
nmint = len(D["cr_slot"]); gmax = np.zeros(nmint)
np.maximum.at(gmax, D["mint"], vs)
# future max px after each row (reverse cummax within mint)
N = len(px); seg_rank = np.repeat(np.arange(len(D["span_a"])), D["span_b"] - D["span_a"])
lp = np.where((vt > 1e12) & (vs > 1), np.log(np.maximum(px, 1e-30)), -60.0); off = (seg_rank.max() - seg_rank)[::-1] * 1000.0          # increasing along the reversed order -> cummax resets per mint
rev = lp[::-1] + off
fmax = (np.maximum.accumulate(rev) - off)[::-1]
U = dict(np.load(f"{OUT}/U.npz")); Sc = np.load(f"{OUT}/s9_scores.npz")
U["grad"] = gmax[U["mint"]] >= 84; U["x2"] = np.exp(fmax[U["row"]] - lp[U["row"]]) >= 2
tmax = U["bt"].max(); TE = U["bt"] >= tmax - 6 * 3600
y = U["y3"].astype(bool) & (U["my_buys"] == 0); wt = np.where(y, 1.0, 25.0)
for f in ("LDUMP", "LPUMP", "EDUMP", "EPUMP", "MFLOW"):
    R = Sc[f + "_rows"]; s = Sc[f + "_s"]; yy = y[R]; ww = wt[R]; te = TE[R]
    g = U["grad"][R]; x2 = U["x2"][R]
    av = lambda m, v, w_=None: np.average(v[m], weights=(ww if w_ is None else w_)[m]) if m.any() else np.nan
    st = s[te]; o = np.argsort(-st); cw = np.cumsum(ww[te][o]); k = np.searchsorted(cw, yy[te].sum() * 3)
    top = np.zeros(te.sum(), bool); top[o[:k]] = True; nh = top & ~yy[te]
    print(f"{f}: graduates  his {av(yy, g):.3f}  skipped {av(~yy, g):.3f}  model-top3x-not-his(TEST) {av(nh, g[te], ww[te]):.3f} | reaches 2x  his {av(yy, x2):.3f}  skipped {av(~yy, x2):.3f}  model-not-his {av(nh, x2[te], ww[te]):.3f}")
