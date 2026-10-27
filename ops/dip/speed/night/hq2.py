#!/usr/bin/env python3
# Value model across DAYS: train on 10-23 (7 h), validate on the first 15% of 10-24, TEST on the rest of 10-24 (~6 h, never seen).
# Same features / replay as hqmodel.py (entry +OFF txs after the dump, hold 6, 0.3 SOL, +5% guard, 20% follower cut).
import json, collections, bisect, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip"); import gbdt_np as G
S = 0.3e9; FEE = 0.0125
def load(fn):
    rows = json.load(open(fn)); T = collections.defaultdict(list)
    for r in rows:
        if not r[4]: continue
        for t in r[11]:
            if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6], r[13]))
    for m in T: T[m].sort()
    return T
def replay(v, keys, s, i, off, hold, cost):
    kp = bisect.bisect_left(keys, (s, i + 1)) - 1; ke = bisect.bisect_left(keys, (s, i + 1 + off)) - 1
    if kp < 0 or ke < 0: return None
    pv, ev = v[kp], v[ke]
    if (ev[6] / ev[7]) / (pv[6] / pv[7]) > 1.05: return -0.0005 * cost / 0.002
    x = S * (1 - FEE); q = ev[7] * x / (ev[6] + x)
    kx = bisect.bisect_left(keys, (s + hold + 1, 0)) - 1; xv = v[kx]
    p = ((xv[6] + x) * q / xv[7] * (1 - FEE) - S) / 1e9 - cost
    return p * 0.8 if p > 0 else p
def vm_feats(v, slots, k):
    """the 16 VM1 features of the dump v[k] (v: a token's SOL-curve trades in chain order: (slot, idx, user, buy, sol, tok, vsol, vtok, bt))"""
    x = v[k]; s = x[0]; a5, a15, a60 = (bisect.bisect_left(slots, s - n) for n in (24, 70, 282))
    p = lambda y: y[6] / y[7]; pre15 = v[a15:k]; pre60 = v[a60:k]
    drop = 1 - p(x) / ((x[6] + x[4]) / max(x[7] - x[5], 1))
    return [x[4] / 1e9, drop, x[6] / 1e9, (s - v[0][0]) * 0.2126, sum(y[4] for y in pre15 if y[3]) / 1e9, sum(y[4] for y in pre15 if not y[3]) / 1e9,
            len({y[2] for y in v[a5:k] if y[3]}), len({y[2] for y in pre15 if y[3]}), k, (s - v[k - 1][0]) * 0.2126 if k else 99,
            p(x) / p(v[a15]) - 1 if a15 < k else 0, p(x) / p(v[a60]) - 1 if a60 < k else 0, max(y[6] for y in v[:k + 1]) / 1e9,
            float(k < 3), sum(1 for y in pre60 if not y[3] and y[4] >= 1e9), float(any(y[2] == x[2] and y[3] for y in v[:k]))]
def dataset(T, off=80, cost=0.002):
    X, V, TS = [], [], []
    for m, v in T.items():
        slots = [x[0] for x in v]; keys = [(x[0], x[1]) for x in v]
        for k, x in enumerate(v):
            if x[3] or x[4] < 1e9: continue
            val = replay(v, keys, x[0], x[1], off, 6, cost)
            if val is None: continue
            X.append(vm_feats(v, slots, k)); V.append(val); TS.append(x[0])
    o = np.argsort(TS)
    return np.array(X, float)[o], np.array(V)[o], np.array(TS)[o]
if __name__ == "__main__":
    A = load("rows_d23.json"); B = load("race_rows.json")
    for off in (80, 40):
        for cost in (0.002, 0.0006):
            Xa, Va, Ta = dataset(A, off, cost); Xb, Vb, Tb = dataset(B, off, cost)
            X = np.vstack([Xa, Xb]); V = np.concatenate([Va, Vb]); n = len(V); na = len(Va)
            TR = np.zeros(n, bool); TR[:na] = True; VA = np.zeros(n, bool); VA[na: na + int(len(Vb) * .15)] = True; TE = ~(TR | VA)
            hours = (Tb.max() - Tb[int(len(Vb) * .15)]) * 0.2126 / 3600
            Bm = G.binize(X, TR); y = (V > 0).astype(float)
            trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
            te = np.where(TE)[0]; order = te[np.argsort(-f[te])]
            print(f"\ntrain 10-23 ({na} dumps) -> TEST 10-24 {hours:.1f} h ({TE.sum()} dumps) | entry +{off} txs, cost {cost} | AUC test {G.auc(y[TE], f[TE]):.3f}")
            for k in (100, 300, 600, 1200):
                pick = order[:k]; half = np.median(pick)
                h1 = V[pick[pick < half]].sum(); h2 = V[pick[pick >= half]].sum()
                print(f"   top {k:4d} ({k/hours:4.0f}/h): total {V[pick].sum():+6.2f} SOL | per trade {V[pick].mean():+.4f} | {V[pick].sum()/hours*24:+6.1f} SOL/day | halves {h1:+.2f} / {h2:+.2f}")
