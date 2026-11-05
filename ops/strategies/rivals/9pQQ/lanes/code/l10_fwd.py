#!/usr/bin/env python3
"""LANES step 10: forward price moves for every sampled decision moment: price after the last trade at or before slot s+H divided by the
price right after the moment's trade, H in (1, 5, 20, 80, 300); plus max/min over the next 300 slots. -> lanes/momfwd_<run>.npy"""
import sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
run = sys.argv[1]; K, V = llib.K, llib.V
z = np.load(f"{llib.D}/mom_{run}.npz"); ids = z["ids"]
t = llib.load(run)
# 9pQQ removed: add back its held tokens (cumulative own token delta per mint) to the curve balance
own = np.where(t.u == t.wid, t.tok.astype(float), 0.0)
cum = np.cumsum(own); starts = t.ms[t.m]; base = np.where(starts > 0, cum[np.maximum(starts - 1, 0)], 0.0)
held = cum - base
held = np.where(np.arange(len(cum)) >= starts, held, 0.0)
# first row of each mint: base must be cum before mint start
cpa = t.cpost.astype(float) + held
P = (K / (cpa + V)) / (cpa + V)
HS = (1, 5, 20, 80, 300); out = np.full((len(ids), len(HS) + 2), np.nan, np.float32)
for k, (m, row) in enumerate(ids):
    a, b = t.ms[m], t.ms[m + 1]; s0 = t.s[row]; p0 = P[row]
    for h, H in enumerate(HS):
        e = a + int(np.searchsorted(t.s[a:b], s0 + H, side="right")) - 1
        out[k, h] = P[e] / p0 - 1
    e = a + int(np.searchsorted(t.s[a:b], s0 + 300, side="right"))
    seg = P[row + 1:e]
    if len(seg): out[k, -2] = seg.max() / p0 - 1; out[k, -1] = seg.min() / p0 - 1
np.save(f"{llib.D}/momfwd9_{run}.npy", out); print(run, len(ids), flush=True)
