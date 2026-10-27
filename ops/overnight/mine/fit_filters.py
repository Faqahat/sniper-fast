#!/usr/bin/env python3
# Same pattern mine, but a separate model per FILTERED subset of moments. Train R2 (last 20% = validation), test R3 and R4 (unseen).
# Target: our 1 SOL trade (75 ms landing) made > +1% after h s (h = 3 and 10). Report baseline (buy every moment in the subset) and top picks.
import pickle, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); import gbdt_np as G
D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
X = np.concatenate([D["X"], D4["X"]]); Y = np.concatenate([D["Y"], D4["Y"]]); M = D["M"] + D4["M"]; F = D["F"]; fi = {f: i for i, f in enumerate(F)}
run = np.array([m[2] for m in M]); t = np.array([m[3] for m in M], float); tok = np.array([m[0] for m in M])
c = lambda n: X[:, fi[n]]
FILTERS = {"after_sell": c("trig_buy") == 0, "after_buy": c("trig_buy") == 1, "young<=60s": c("age") <= 60, "older60-900s": c("age") > 60,
           "winner_bought10s": c("w10") >= 1, "big_trigger>=1": c("trig_sol") >= 1, "quiet_gap>=3s": c("gap") >= 3, "tweet_tokens": c("tweet_host") == 1,
           "curve30-45": (c("vsol") >= 30) & (c("vsol") < 45), "curve45-80": (c("vsol") >= 45) & (c("vsol") < 80)}
name = sys.argv[1]; flt = FILTERS[name]
tr_all = (run == "R2") & flt; cut = np.quantile(t[tr_all], 0.8); tr = tr_all & (t <= cut); va = tr_all & (t > cut); te = (run == "R3") & flt; te4 = (run == "R4") & flt
H4 = D4["hours"]
def nonoverlap(ix, hold):
    keep = []; last = {}
    for i in ix[np.argsort(t[ix])]:
        if tok[i] in last and t[i] - last[tok[i]] < hold: continue
        keep.append(i); last[tok[i]] = t[i]
    return np.array(keep, int)
print(f"##### FILTER {name}: train {tr.sum()} val {va.sum()} | test R3 {te.sum()} | test R4 {te4.sum()} ({H4:.1f} h)")
print("  baseline buy-every-moment, per trade:", " | ".join(f"{h}s R3 {Y[te, j].mean():+.4f} R4 {Y[te4, j].mean():+.4f}" for j, h in enumerate((1, 3, 10, 30))))
Bm = G.binize(X.astype(float), tr)
for j, h in ((1, 3), (2, 10)):
    y = (Y[:, j] > 0.01).astype(float)
    trees, f = G.fit(Bm, y, tr, va, rounds=400, lr=0.05, depth=4)
    print(f"  == hold {h}s: trees {len(trees)} | AUC val {G.auc(y[va], f[va]):.3f} R3 {G.auc(y[te], f[te]):.3f} R4 {G.auc(y[te4], f[te4]):.3f}", flush=True)
    for q in (0.005, 0.01, 0.02, 0.05, 0.10):
        thr = np.quantile(f[va], 1 - q); cells = []
        for part, mask, hrs in (("VAL", va, None), ("R3", te, 24.0), ("R4", te4, H4)):
            ix = nonoverlap(np.where(mask & (f >= thr))[0], max(h, 3))
            if not len(ix): cells.append(f"{part} n=0"); continue
            pk = Y[ix, j]; extra = f" pess3s {Y[ix, 4].sum():+.1f}" if h == 3 else ""
            cells.append(f"{part} n={len(ix):4d} {pk.sum():+7.1f} ({pk.mean():+.3f}/tr, win {np.mean(pk > 0):.0%}{', ' + format(pk.sum() / hrs * 24, '+.1f') + '/day' if hrs else ''}{extra})")
        print(f"     top {q:5.1%} | " + " | ".join(cells), flush=True)
