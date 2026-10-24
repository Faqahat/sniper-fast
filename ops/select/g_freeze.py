#!/usr/bin/env python3
# FREEZE the paper-test strategies on run-1 data only (read-only, offline). Saves model trees, bin edges, feature list,
# score thresholds and the simple filters to frozen.json. Nothing here looks at the forward run.
# usage: python3 g_freeze.py <table.jsonl.gz> <out frozen.json> <entry> <exit col suffix> [FIX]
import sys, os, json
sys.argv = [sys.argv[0], sys.argv[1], os.path.dirname(sys.argv[2]) or ".", sys.argv[5] if len(sys.argv) > 5 else "0.015", sys.argv[2], sys.argv[3], sys.argv[4]]
OUTF, EN, EX = sys.argv[4], sys.argv[5], sys.argv[6]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_model.py")).read()
exec(src[:src.index("REPORT = {}")])
fk = [k for k, (tt, _) in cols.items() if tt in ENT[EN]]
if os.environ.get("FEATSET") == "liveh":       # live model: raw-tx + own create stream + lagged outcome history; no RPC, no tx meta
    fk = [k for k in fk if cols[k][0] in ("T0", "T0b", "H") and not k.startswith("h_fd") and k not in ("create_cu", "create_idx")]
if os.environ.get("FEATSET") in ("liveh2", "liveh3"):   # liveh minus create_fee: the tx-meta fee is not knowable before execution for ~1/3 of creates
    fk = [k for k in fk if cols[k][0] in ("T0", "T0b", "H") and not k.startswith("h_fd") and k not in ("create_cu", "create_idx", "create_fee")]
    if os.environ.get("FEATSET") == "liveh2": fk = [k for k in fk if not k.startswith("hd_")]   # liveh3 = + anti-dump behaviour history (f_dump.py)
X = np.column_stack([cols[k][1] for k in fk])
# train on the first 80% of run 1, early-stop on the last 20%; thresholds from that holdout's score distribution
trn = idx < int(N * .8); hol = idx >= int(N * .8)
edges = []
for j in range(X.shape[1]):
    x = X[:, j]; xt = x[trn & ~np.isnan(x)]
    edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
Bm = np.zeros(X.shape, np.int16)
for j in range(X.shape[1]):
    b = np.searchsorted(np.array(edges[j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
net = g(f"{EN}_{EX}") - FIX / SIZE; ok = ~np.isnan(net); y = (net > 0).astype(float)
if os.environ.get("LABEL") == "good":          # good token: not a fast dump (<=0.85x within 5 s) and up at 30 s / peaks >=1.5x
    yg = g("y_good"); ok = ok & ~np.isnan(yg); y = np.nan_to_num(yg)
if os.environ.get("LABEL") == "dump":          # fast-dump classifier (a veto): price <= 0.85x of the post-bundle price within 5 s
    yg = g("y_dump5"); ok = ok & ~np.isnan(yg); y = np.nan_to_num(yg)
trees, f = fit(Bm, y, trn & ok, hol & ok)
p0 = y[trn & ok].mean()
thr = {f"{q:.0%}": float(np.quantile(f[hol & ok], 1 - q)) for q in (0.005, 0.01, 0.02, 0.05)}
hold = {k: stats(net[hol & ok & (f >= v)]) for k, v in thr.items()}
json.dump(dict(featset=os.environ.get("FEATSET", "full"), label=os.environ.get("LABEL", "net>0"), entry=EN, exit=EX, fix=FIX, features=fk, edges=edges, trees=trees, F0=float(np.log(p0 / (1 - p0))), lr=0.05, thresholds=thr, holdout=hold,
               trained_on="run_20261021_2207 first 80%", n_trees=len(trees)), open(OUTF, "w"))
print(f"frozen {EN} {EX}: {len(trees)} trees, {len(fk)} features; holdout top-k: " + "; ".join(f"{k}: n={v['n']} mean={v['mean']:+.3f}" for k, v in hold.items() if v))
