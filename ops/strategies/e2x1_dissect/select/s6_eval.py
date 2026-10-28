#!/usr/bin/env python3
"""SELECT s6: value of his picks vs the model's picks on the TEST 6 h (OOS). Unit = (mint, slot) moment: score = max event score in
that slot on the mint; label = he bought within 1 slot of any event of the moment. Forward = market px change from the moment's
last event px to +2/+5/+24/+141 slots (f*) and from one slot later (g*). Negatives are a 4 % sample (weight 25)."""
import numpy as np, json
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
U = np.load(f"{OUT}/U.npz"); Sc = np.load(f"{OUT}/s4_scores.npz")
rows = Sc["rows"]; te = Sc["te"]; s = Sc["s"]
r = rows[te]; s = s[te]
y = U["y"][r]; mint = U["mint"][r]; slot = U["slot"][r]
key = mint.astype(np.int64) * 10**10 + slot
o = np.lexsort((-s, key)); k2 = key[o]; first = np.r_[True, k2[1:] != k2[:-1]]
# moment = first (highest score) event; label = any y in the moment
ym = np.maximum.reduceat(y[o].astype(int), np.flatnonzero(first)).astype(bool)
idx = r[o][first]; sm = s[o][first]
f = {k: U[k][idx].astype(float) for k in ("f2", "f5", "f24", "f141", "g24", "g141", "age_s", "vsol")}
wt = np.where(ym, 1.0, 25.0)
print(f"test moments: his {ym.sum()}, others (weighted) {wt[~ym].sum():.0f}")
def stats(m, t):
    w_ = wt[m]
    out = [t, int(m.sum()), f"{w_.sum():.0f}"]
    for k in ("f5", "f24", "f141", "g24", "g141"):
        x = f[k][m]; ok = np.isfinite(x); out.append(f"{100*np.average(np.clip(x[ok],-1,5), weights=w_[ok]):+.2f}")
    print("  ".join(str(z) for z in out))
print("set  n  weighted_n  f5  f24  f141  g24(entry+1slot)  g141   (mean %, market px, no fees)")
stats(ym, "HIS picks")
stats(np.ones(len(ym), bool), "ALL moments")
o2 = np.argsort(-sm); cw = np.cumsum(wt[o2])
for mult in (1, 2, 5):
    k = np.searchsorted(cw, ym.sum() * mult)
    top = np.zeros(len(ym), bool); top[o2[:k]] = True
    stats(top, f"MODEL top (rate x{mult})"); stats(top & ~ym, f"  model top x{mult} NOT his"); print(f"  recall of his = {(top & ym).sum() / ym.sum():.2f}")
