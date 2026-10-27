#!/usr/bin/env python3
# "Copy haqqiUUX's selection": every >= 1 SOL dump (SOL curves, 7 h chain) -> features known AT the dump -> (1) label = he bought
# within 10 slots, (2) value = our replayed trade at +80 txs, hold 6, 0.3 SOL (20% follower cut, +5% guard). Time split:
# train first 50%, validation next 15%, TEST last 35% (never seen). Pick the top dumps by each model on TEST.
import json, collections, bisect, pickle, sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip"); import gbdt_np as G
exec(open("replay_hq.py").read().split("hours = ")[0])
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
X, Y, V, TS, KEY = [], [], [], [], []
NAMES = ["sell", "drop", "curve", "age", "flow15", "sells15", "buyers5", "buyers15", "ntr", "gap_last", "ch15", "ch60", "max_curve", "dev_like", "n_bigsells60", "seller_bought"]
for m, v in T.items():
    slots = [x[0] for x in v]; keys = [(x[0], x[1]) for x in v]
    hq = [x for x in v if x[2] == W and x[3]]
    for k, x in enumerate(v):
        if x[3] or x[4] < 1e9: continue
        s = x[0]
        a5, a15, a60 = (bisect.bisect_left(slots, s - n) for n in (24, 70, 282))
        p = lambda y: y[6] / y[7]
        pre15 = v[a15:k]; pre60 = v[a60:k]
        drop = 1 - p(x) / ((x[6] + x[4]) / max(x[7] - x[5], 1))
        f = [x[4] / 1e9, drop, x[6] / 1e9, (s - v[0][0]) * 0.2126, sum(y[4] for y in pre15 if y[3]) / 1e9, sum(y[4] for y in pre15 if not y[3]) / 1e9,
             len({y[2] for y in v[a5:k] if y[3]}), len({y[2] for y in pre15 if y[3]}), k, (s - v[k - 1][0]) * 0.2126 if k else 99,
             p(x) / p(v[a15]) - 1 if a15 < k else 0, p(x) / p(v[a60]) - 1 if a60 < k else 0, max(y[6] for y in v[:k + 1]) / 1e9,
             float(k < 3), sum(1 for y in pre60 if not y[3] and y[4] >= 1e9), float(any(y[2] == x[2] and y[3] for y in v[:k]))]
        took = any(s <= y[0] <= s + 10 and (y[0], y[1]) > (x[0], x[1]) for y in hq)
        val = replay(v, s, x[1], 80, 6)
        if val is None: continue
        X.append(f); Y.append(took); V.append(val); TS.append(s); KEY.append((m, s, x[1]))
X = np.array(X, float); Y = np.array(Y, float); V = np.array(V); TS = np.array(TS)
o = np.argsort(TS); X, Y, V, TS = X[o], Y[o], V[o], TS[o]; KEY = [KEY[j] for j in o]; n = len(Y)
TR = np.zeros(n, bool); TR[: int(n * .5)] = True; VA = np.zeros(n, bool); VA[int(n * .5): int(n * .65)] = True; TE = ~(TR | VA)
hours_te = (TS[TE].max() - TS[TE].min()) * 0.2126 / 3600
print(f"dumps {n} | haqqi took {Y.mean():.1%} | test window {hours_te:.1f} h ({TE.sum()} dumps)")
Bm = G.binize(X, TR)
trees, f = G.fit(Bm, Y, TR, VA, rounds=400, lr=0.05, depth=3)
print(f"IMITATE haqqi: AUC val {G.auc(Y[VA], f[VA]):.3f} test {G.auc(Y[TE], f[TE]):.3f}")
acc = collections.defaultdict(float)
for t in trees: G.imp(t, acc)
print("  top features:", [NAMES[j] for j, _ in sorted(acc.items(), key=lambda kv: -kv[1])[:8]])
# value model: is our trade profitable at our landing?
Yv = (V > 0).astype(float); trees2, f2 = G.fit(Bm, Yv, TR, VA, rounds=400, lr=0.05, depth=3)
print(f"VALUE model (our trade > 0 at +80 txs): AUC val {G.auc(Yv[VA], f2[VA]):.3f} test {G.auc(Yv[TE], f2[TE]):.3f}")
for name, sc in (("imitate haqqi", f), ("value model", f2), ("haqqi's ACTUAL picks", Y * 10 + np.random.default_rng(0).random(n))):
    te = np.where(TE)[0]; order = te[np.argsort(-sc[te])]
    for k in (50, 100, 200, 400, 800):
        pick = order[:k]
        print(f"  {name:20s} top {k:4d} on TEST ({k/hours_te:5.0f}/h): total {V[pick].sum():+7.2f} SOL | per trade {V[pick].mean():+.4f} | win {(V[pick]>0).mean():.0%} | {V[pick].sum()/hours_te*24:+7.1f} SOL/day")
pickle.dump(dict(X=X, Y=Y, V=V, TS=TS, f=f, f2=f2, names=NAMES, KEY=KEY, TE=TE), open("hqmodel.pkl", "wb"))
# ---- owner: cheaper sends (lower priority + one small tip) and pre-send (entry at the dump itself)
te = np.where(TE)[0]; order = te[np.argsort(-f2[te])]
print("\nVALUE model picks on TEST: cost per filled trip (tx+tips) and entry position")
for k in (100, 200, 400):
    pick = order[:k]
    for off in (0, 40, 80):
        base = []
        for j in pick:
            m, s0, i0 = KEY[j]; r = replay(T[m], s0, i0, off, 6)
            base.append(r if r is not None else 0)
        base = np.array(base)
        for cost in (0.002, 0.001, 0.0006):
            adj = np.where(base == -0.0005, -0.0005 * cost / 0.002, np.where(base > 0, (base / 0.8 + 0.002 - cost) * 0.8, base + 0.002 - cost))
            print(f"  top {k:3d} ({k/hours_te:4.0f}/h) entry +{off:2d} txs{' (PRE-SEND upper bound)' if off == 0 else '':24s} cost {cost:.4f}: total {adj.sum():+6.2f} SOL | per trade {adj.mean():+.4f} | {adj.sum()/hours_te*24:+6.1f} SOL/day")
