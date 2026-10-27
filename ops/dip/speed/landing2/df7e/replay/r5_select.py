#!/usr/bin/env python3
# DF7e replay step 5: can his SELECTION be written as explicit causal rules? (read-only)
# Base events (broad): dump = sell >= 0.3 SOL moving the price >= 3%; buy >= 0.5 SOL; curve <= 50; creation in recording.
# Target: the event is one of his trigger events (his_triggers.json). Features use only trades up to and including the event.
# A small depth-3 tree (my own code, gini, min leaf 300) is fit on the FIRST half of his life and scored on the second half.
# Writes sel.npz: base event indices, features, his flag, tree score (take rate of the leaf, fit on half 1).
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import rlib, core
D = rlib.load(); T = D.T; n = len(T)
sol = T["sol"] / 1e9; ages = D.age * core.SLOT_SEC
mint = T["mint"].astype(np.int64); slot = T["slot"].astype(np.int64)
base = D.full_hist[T["mint"]] & (D.curve <= 50) & D.chain_ok & (((T["buy"] == 0) & (sol >= 0.3) & (D.drop >= 0.03)) | ((T["buy"] == 1) & (sol >= 0.5)))
sg = np.where(T["buy"] == 1, 1.0, -1.0) * sol
cs = np.cumsum(sg)
def win_start(L):
    return np.searchsorted(D.G, core.pack(T["mint"], np.maximum(slot - L, core.S0 + 1), 0, 0), "left")
k = np.arange(n)
st = D.mstart[T["mint"]]
F = {}
for L in (5, 25, 150):
    a = np.maximum(win_start(L), st)
    F[f"flow{L}"] = np.where(k > a, cs[k - 1] - np.where(a > 0, cs[np.maximum(a - 1, 0)], 0), 0.0) * (k > a)
    F[f"ntr{L}"] = (k - a).astype(float)
    vprev = np.where(a - 1 >= st, T["vsol"][np.maximum(a - 1, 0)].astype(float), 30e9)
    F[f"ch{L}"] = (T["vsol"].astype(float) / vprev) ** 2 - 1
off = mint.astype(float) * 1e12
pk = np.maximum.accumulate(off + T["vsol"].astype(float)) - off
F["dd_peak"] = 1 - (T["vsol"].astype(float) / pk) ** 2
F["peak_curve"] = pk / 1e9 - 30
F["ntr"] = (k - st).astype(float)
F["sol"] = sol; F["drop"] = D.drop; F["curve"] = D.curve; F["age"] = ages; F["gap"] = np.minimum(D.gap, 10**5).astype(float); F["isbuy"] = T["buy"].astype(float)
# seller / buyer had bought this token before; trader is the creator (first trade's user)
o = np.lexsort((k, T["user"], T["mint"]))
grp = np.ones(n, bool); grp[1:] = (T["mint"][o][1:] != T["mint"][o][:-1]) | (T["user"][o][1:] != T["user"][o][:-1])
b = (T["buy"][o] == 1).astype(np.int64); cb = np.cumsum(b); gs = np.maximum.accumulate(np.where(grp, np.arange(n), 0))
prior_buys = cb - b - np.where(gs > 0, cb[gs - 1], 0) + np.where(gs > 0, 0, 0)
pb = np.zeros(n); pb[o] = prior_buys - np.where(gs > 0, 0, 0)
# fix: cb[gs-1] for gs==0 must be 0
pb2 = np.zeros(n); pb2[o] = cb - b - np.where(gs > 0, cb[np.maximum(gs - 1, 0)], 0)
F["trader_prior_buys"] = pb2
F["is_creator"] = (T["user"] == T["user"][st]).astype(float)
NAMES = list(F)
idx = np.where(base)[0]
X = np.stack([F[f][idx] for f in NAMES], 1)
HT = np.unique([r[0] for r in json.load(open(rlib.DD + "/his_triggers.json"))])
y = np.isin(idx, HT)
HIS = json.load(open(rlib.DD + "/his_triggers.json")); HS0 = min(r[3] for r in HIS); HS1 = max(r[3] for r in HIS); HMID = (HS0 + HS1) // 2
s_ = slot[idx]
h1 = (s_ >= HS0) & (s_ <= HMID); h2 = (s_ > HMID) & (s_ <= HS1)
print(f"base events {len(idx)} | in his life {np.sum(h1 | h2)}, his triggers among them {y[h1 | h2].sum()} (of {len(HT)}) take {y[h1 | h2].mean():.4f}")
# --- tiny tree ---
def fit(X, y, depth=3, minleaf=300):
    def gini(p): return 2 * p * (1 - p)
    def build(ix, d):
        p = y[ix].mean()
        node = {"p": float(p), "n": int(len(ix))}
        if d == 0 or len(ix) < 2 * minleaf: return node
        best = None
        for j in range(X.shape[1]):
            x = X[ix, j]
            qs = np.unique(np.quantile(x, np.linspace(0.05, 0.95, 19)))
            for t in qs:
                l = x <= t; nl = l.sum(); nr = len(ix) - nl
                if nl < minleaf or nr < minleaf: continue
                pl = y[ix][l].mean(); pr = y[ix][~l].mean()
                g = (nl * gini(pl) + nr * gini(pr)) / len(ix)
                if best is None or g < best[0]: best = (g, j, float(t))
        if best is None or best[0] >= gini(p) - 1e-6: return node
        _, j, t = best; l = X[ix, j] <= t
        node.update(f=j, t=t, l=build(ix[l], d - 1), r=build(ix[~l], d - 1)); return node
    return build(np.arange(len(y)), depth)
def score(node, X):
    out = np.zeros(len(X)); st_ = [(node, np.arange(len(X)))]
    while st_:
        nd, ix = st_.pop()
        if "f" not in nd: out[ix] = nd["p"]; continue
        l = X[ix, nd["f"]] <= nd["t"]; st_.append((nd["l"], ix[l])); st_.append((nd["r"], ix[~l]))
    return out
def show(nd, pre=""):
    if "f" not in nd: print(f"{pre}leaf n={nd['n']} take={nd['p']:.3f}"); return
    print(f"{pre}{NAMES[nd['f']]} <= {nd['t']:.4g}  (n={nd['n']} take={nd['p']:.3f})"); show(nd["l"], pre + "  "); show(nd["r"], pre + "  ")
for depth in (3, 4):
    tree = fit(X[h1], y[h1], depth)
    print(f"\n== depth {depth}, fit on his first half"); show(tree)
    sc = score(tree, X)
    for nm, m in (("half1 (fit)", h1), ("half2 (test)", h2)):
        o_ = np.argsort(-sc[m]); yy = y[m][o_]
        for frac in (0.02, 0.05, 0.1):
            kk = int(frac * m.sum()); print(f"   {nm}: top {frac:.0%} by score holds {yy[:kk].sum() / max(y[m].sum(), 1):.0%} of his triggers (take {yy[:kk].mean():.3f} vs base {y[m].mean():.4f})")
    if depth == 3: json.dump(tree, open(rlib.DD + "/sel_tree.json", "w")); np.savez(rlib.DD + "/sel.npz", idx=idx, y=y, score=sc, names=np.array(NAMES), X=X.astype(np.float32))
