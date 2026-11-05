#!/usr/bin/env python3
"""Entry edge test: outside net SOL flow in the next K slots after taken buy triggers vs skipped flat triggers,
within the same token-hour and same size / |ch10| buckets (stratified). usage: c12_fwd.py RUN"""
import sys, numpy as np, collections
run = sys.argv[1]
z = np.load(f"/home/moiz/sniper-data/rivals/9pQQ/casebook/scale_{run}.npz", allow_pickle=False)
s = z["s"]; seg = z["seg"]; own = z["own"]; buy = z["buy"]; size = z["size"]; vsol = z["vsol"]
tb = z["tb"]; hold = z["holding"]; age = z["age"]; ss = z["since_sell"]; ch10 = z["ch10"]; ntr = z["ntrips"]
N = len(s)
flow = np.where(~own, np.where(buy, size, -size), 0.0); cf = np.r_[0, np.cumsum(flow)]
key = seg.astype(np.int64) * (1 << 32) + s
elig = (~own) & (~hold) & (age >= 8) & ((ss < 0) | (ss >= 2))
# traded tokens only
tok_traded = np.zeros(seg.max() + 1, bool); tok_traded[seg[own]] = True
elig &= tok_traded[seg]
idx = np.where(elig)[0]
# forward flow excludes own trades; window (s, s+K]
res = {}
for K in (3, 10, 25, 100):
    j1 = np.searchsorted(key, key[idx] + 1, "left"); j2 = np.searchsorted(key, key[idx] + K, "right")
    res[K] = (cf[j2] - cf[j1]) / np.maximum(vsol[idx], 1)
# strata: token x size bucket x |ch10| bucket
sb = np.digitize(size[idx], [0.1, 0.3, 1, 3]); cb = np.digitize(np.abs(np.nan_to_num(ch10[idx])), [2, 5, 10, 20])
st = seg[idx].astype(np.int64) * 100 + sb * 10 + cb
T = tb[idx]
TF = z["tf"][idx] & ~T
for K in (3, 10, 25, 100):
    f = res[K]; d = collections.defaultdict(lambda: [[], []])
    for g, t, v in zip(st, T, f): d[g][int(t)].append(v)
    diffs = []; w = []
    for g, (a, b) in d.items():
        if a and b: diffs.append(np.mean(b) - np.mean(a)); w.append(len(b))
    diffs = np.array(diffs); w = np.array(w)
    print(f"   failed-buy triggers n={TF.sum()}: mean fwd {100*f[TF].mean():+.3f}%  (skipped excl. failed {100*f[~T & ~TF].mean():+.3f}%)")
    print(f"{run} K={K:3d}: taken mean fwd flow/vsol {100*f[T].mean():+.3f}% skipped {100*f[~T].mean():+.3f}% | stratified diff (taken-skipped) {100*np.average(diffs,weights=w):+.3f}% over {w.sum()} taken in {len(w)} strata; frac strata taken>skipped {np.mean(diffs>0):.2f}")
