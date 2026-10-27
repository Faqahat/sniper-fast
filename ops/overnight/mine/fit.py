#!/usr/bin/env python3
# Fit gradient-boosted models on R2 (train; last 20% by time = validation for early stop + threshold), test on R3 (never seen).
# Target per hold h: our 1 SOL trade (75 ms landing) made > +1% after h seconds. Picks = score above the validation threshold for top-q.
import pickle, numpy as np, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); import gbdt_np as G
D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
X = np.concatenate([D["X"], D4["X"]]); Y = np.concatenate([D["Y"], D4["Y"]]); M = D["M"] + D4["M"]; F = D["F"]
JOBS = [int(a) for a in sys.argv[1:]] or [0, 1, 2, 3]
run = np.array([m[2] for m in M]); t = np.array([m[3] for m in M], float); tok = np.array([m[0] for m in M])
tr_all = run == "R2"; te = run == "R3"; te4 = run == "R4"
cut = np.quantile(t[tr_all], 0.8); tr = tr_all & (t <= cut); va = tr_all & (t > cut)
Bm = G.binize(np.nan_to_num(X.astype(float), nan=np.nan), tr)
print(f"rows: train {tr.sum()} | val {va.sum()} | test {te.sum()} | base win (>1% at 3 s) train {np.mean(Y[tr, 1] > 0.01):.1%} test {np.mean(Y[te, 1] > 0.01):.1%}")
print(f"buy-everything baseline, test (R3 24 h), per trade: " + " | ".join(f"{h}s {Y[te, j].mean():+.4f}" for j, h in enumerate(D['H'])))
def nonoverlap(ix, hold):
    keep = []; last = {}
    for i in ix[np.argsort(t[ix])]:
        if tok[i] in last and t[i] - last[tok[i]] < hold: continue
        keep.append(i); last[tok[i]] = t[i]
    return np.array(keep, int)
for j, h in [(j, (1, 3, 10, 30)[j]) for j in JOBS]:
    y = (Y[:, j] > 0.01).astype(float)
    trees, f = G.fit(Bm, y, tr, va, rounds=500, lr=0.05, depth=4)
    print(f"\n=== hold {h}s: trees {len(trees)} | AUC val {G.auc(y[va], f[va]):.3f} | test R3 {G.auc(y[te], f[te]):.3f} | test R4 {G.auc(y[te4], f[te4]):.3f}", flush=True)
    for q in (0.002, 0.005, 0.01, 0.02, 0.05):
        thr = np.quantile(f[va], 1 - q)
        for part, mask in (("VAL     ", va), ("TEST R3 ", te), ("TEST R4 ", te4)):
            ix = nonoverlap(np.where(mask & (f >= thr))[0], max(h, 3))
            if not len(ix): continue
            pk = Y[ix, j]; pess = Y[ix, 4] if h == 3 else None
            print(f"   top {q:5.1%} {part} n={len(ix):5d} | kept: total {pk.sum():+8.2f} per trade {pk.mean():+.4f} win {np.mean(pk > 0):.0%}"
                  + (f" | pessimistic 3s: {pess.sum():+8.2f} ({pess.mean():+.4f})" if pess is not None else ""))
    if h == 3:
        acc = np.zeros(X.shape[1])
        for tt in trees: G.imp(tt, acc)
        print("   top features:", [(F[i], round(acc[i] / acc.sum(), 3)) for i in np.argsort(-acc)[:15]])
        thr = np.quantile(f[va], 0.99); sel = te & (f >= thr)
        print("   what the top-1% TEST picks look like (median pick vs median all):")
        for i in np.argsort(-acc)[:12]:
            print(f"      {F[i]:14s} picks {np.nanmedian(X[sel, i]):9.3f} | all {np.nanmedian(X[te, i]):9.3f}")
