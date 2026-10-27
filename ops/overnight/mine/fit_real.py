#!/usr/bin/env python3
# Train on R2 (target = optimistic label at landing LAT / hold HOLD > +1%), test R3 + R4, report picks with: optimistic (followers kept),
# REALISTIC (each follower within 2 slots keeps its own slippage limit; labels_real.pkl). Saves scores to scores_{LAT}_{HOLD}.npy.
import pickle, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); import gbdt_np as G
LAT, HOLD = sys.argv[1], sys.argv[2]
D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
X = np.concatenate([D["X"], D4["X"]]); M = D["M"] + D4["M"]
run = np.array([m[2] for m in M]); t = np.array([m[3] for m in M], float); tok = np.array([m[0] for m in M]); H4 = D4["hours"]
if LAT == "75": kept = np.concatenate([D["Y"], D4["Y"]])[:, {"1": 0, "3": 1}[HOLD]]
else:
    L = pickle.load(open("labels_speed.pkl" if LAT in ("20", "35") else "labels_speed2.pkl", "rb")); kept = L["Y"][:, L["cols"].index(f"{LAT}ms_{HOLD}s")]
R = pickle.load(open("labels_real.pkl", "rb")); real = R["Y"][:, R["cols"].index(f"{LAT}ms_{HOLD}s_real")]
ok = ~np.isnan(kept) & ~np.isnan(real)
tr_all = (run == "R2") & ok; cut = np.quantile(t[tr_all], 0.8); tr = tr_all & (t <= cut); va = tr_all & (t > cut); te = (run == "R3") & ok; te4 = (run == "R4") & ok
def nonoverlap(ix, hold=3):
    keep = []; last = {}
    for i in ix[np.argsort(t[ix])]:
        if tok[i] in last and t[i] - last[tok[i]] < hold: continue
        keep.append(i); last[tok[i]] = t[i]
    return np.array(keep, int)
y = (np.nan_to_num(kept) > 0.01).astype(float); Bm = G.binize(X.astype(float), tr)
trees, f = G.fit(Bm, y, tr, va, rounds=400, lr=0.05, depth=4); np.save(f"scores_{LAT}_{HOLD}.npy", f)
print(f"##### landing {LAT} ms, hold {HOLD} s | every moment per trade R3: optimistic {np.mean(kept[te]):+.4f} realistic {np.mean(real[te]):+.4f} | AUC R3 {G.auc(y[te], f[te]):.3f} R4 {G.auc(y[te4], f[te4]):.3f}", flush=True)
for q in (0.005, 0.01, 0.02, 0.05):
    thr = np.quantile(f[va], 1 - q); cells = []
    for part, mask, hrs in (("VAL", va, 21.8 * 0.2), ("R3", te, 24.0), ("R4", te4, H4)):
        ix = nonoverlap(np.where(mask & (f >= thr))[0])
        if not len(ix): cells.append(f"{part} n=0"); continue
        k = kept[ix]; r = real[ix]
        cells.append(f"{part} n={len(ix):5d} opt {k.sum():+7.1f} ({k.sum()/hrs*24:+6.1f}/d) REAL {r.sum():+7.1f} ({r.mean():+.3f}/tr, win {np.mean(r > 0):.0%}, {r.sum()/hrs*24:+6.1f}/d)")
    print(f"   top {q:5.1%} | " + " | ".join(cells), flush=True)
