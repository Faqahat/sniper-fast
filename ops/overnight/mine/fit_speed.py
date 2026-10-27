#!/usr/bin/env python3
# Train on R2, test on R3 + R4, with labels for a given landing latency (from labels_speed*.pkl, or 75 ms from mine.pkl). Target: > +1% at hold h.
# Reports top-q picks: followers kept (optimistic) and followers in 2 slots after us dropped (pessimistic), per test day, per-day rate.
import pickle, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); import gbdt_np as G
LAT = sys.argv[1]; HOLD = sys.argv[2]           # e.g. 20 1  /  35 3  /  75 1
D = pickle.load(open("mine.pkl", "rb")); D4 = pickle.load(open("mine_r4.pkl", "rb"))
X = np.concatenate([D["X"], D4["X"]]); M = D["M"] + D4["M"]
run = np.array([m[2] for m in M]); t = np.array([m[3] for m in M], float); tok = np.array([m[0] for m in M]); H4 = D4["hours"]
if LAT == "75":
    Y0 = np.concatenate([D["Y"], D4["Y"]]); kept = Y0[:, {"1": 0, "3": 1}[HOLD]]; pess = Y0[:, 4] if HOLD == "3" else np.full(len(kept), np.nan)
else:
    fn = "labels_speed.pkl" if LAT in ("20", "35") else "labels_speed2.pkl"; L = pickle.load(open(fn, "rb")); cols = L["cols"]
    kept = L["Y"][:, cols.index(f"{LAT}ms_{HOLD}s")]; pess = L["Y"][:, cols.index(f"{LAT}ms_{HOLD}s_drop2")]
ok = ~np.isnan(kept)
tr_all = (run == "R2") & ok; cut = np.quantile(t[tr_all], 0.8); tr = tr_all & (t <= cut); va = tr_all & (t > cut); te = (run == "R3") & ok; te4 = (run == "R4") & ok
def nonoverlap(ix, hold=3):
    keep = []; last = {}
    for i in ix[np.argsort(t[ix])]:
        if tok[i] in last and t[i] - last[tok[i]] < hold: continue
        keep.append(i); last[tok[i]] = t[i]
    return np.array(keep, int)
y = (np.nan_to_num(kept) > 0.01).astype(float)
Bm = G.binize(X.astype(float), tr)
trees, f = G.fit(Bm, y, tr, va, rounds=400, lr=0.05, depth=4)
print(f"##### landing {LAT} ms, hold {HOLD} s | buy-every-moment per trade: R3 kept {np.nanmean(kept[te]):+.4f} pess {np.nanmean(pess[te]):+.4f} | R4 kept {np.nanmean(kept[te4]):+.4f} pess {np.nanmean(pess[te4]):+.4f} | AUC R3 {G.auc(y[te], f[te]):.3f} R4 {G.auc(y[te4], f[te4]):.3f}", flush=True)
for q in (0.005, 0.01, 0.02, 0.05, 0.10):
    thr = np.quantile(f[va], 1 - q); cells = []
    for part, mask, hrs in (("VAL", va, 21.8 * 0.2), ("R3", te, 24.0), ("R4", te4, H4)):
        ix = nonoverlap(np.where(mask & (f >= thr))[0])
        if not len(ix): cells.append(f"{part} n=0"); continue
        k = np.nan_to_num(kept[ix]); p = np.nan_to_num(pess[ix])
        cells.append(f"{part} n={len(ix):5d} kept {k.sum():+7.1f} ({k.mean():+.3f}, {k.sum()/hrs*24:+6.1f}/day) pess {p.sum():+7.1f} ({p.sum()/hrs*24:+6.1f}/day)")
    print(f"   top {q:5.1%} | " + " | ".join(cells), flush=True)
