#!/usr/bin/env python3
# Selection trained on OUR execution: per launch, value v = PnL of a 0.5 SOL buy first after the bundle at LAT ms (guard 0.5%,
# pros' later buys removed + follower slippage, sell at 8 s) or -0.005 if the guard refuses. Features = FINAL-2's 61 create-time
# features (paper table_dump). GBDT (logistic, y = v > 0) trained on one run, tested on the other; compared with FINAL-2's own
# picks (offline score, same guards) on the same test launches.
import sys, os, json, gzip, math
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import gbdt_np as G
P = "/home/moiz/sniper-data/collect/paper"; CORE = "/home/moiz/sniper/ops/overnight/core"
LAT = os.environ.get("LAT", "45"); EX = os.environ.get("EX", "t8")
C = json.load(open("/home/moiz/sniper/ops/shadow/final_config2.json"))
M = json.load(open(f"{P}/{C['model_file']}")); MV = json.load(open(f"{P}/{C['veto_file']}")); THR = M["thresholds"][C["top"]]
src = open("/home/moiz/sniper/ops/shadow/paper_live.py").read()
g = {"math": math, "M": M}; exec(src[src.index("def score(x, M=M):"):src.index("# ---- shadow engine timeline")], g); score = g["score"]
FK = M["features"]
def fval(x, k):
    if "==" in k: a, v = k.split("==", 1); return 1.0 if str(x.get(a)) == v else 0.0
    v = x.get(k); return float(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else float("nan")
def guard_ok(r): return r.get("payer_is_creator") == 1 and not ((r.get("glued_n") or 0) == 0 and (r.get("dev_buy") or 0) < 1)
AB = json.load(open(f"{CORE}/allbe.json"))
rows = []
for l in gzip.open(f"{P}/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r.get("quote_sol") != 1 or not r.get("bt") or r.get("mayhem") or r["mint"] not in AB: continue
    a = AB[r["mint"]]; x = a[LAT]["pa"]
    if x is None: continue
    v = x["p"][EX] if x["f"] else -0.005
    rows.append((r, a["run"], v, x["f"]))
rows.sort(key=lambda t: t[0]["bt"])
X = np.array([[fval(r, k) for k in FK] for r, _, _, _ in rows]); V = np.array([t[2] for t in rows]); y = (V > 0).astype(float)
run = np.array([t[1] for t in rows]); fill = np.array([t[3] for t in rows])
guard = np.array([guard_ok(r) for r, _, _, _ in rows])
f2 = np.array([score(r) >= THR and score(r, MV) < C["veto_cut"] and guard_ok(r) for r, _, _, _ in rows])
print(f"launches {len(rows)} (R1 {int((run == 'R1').sum())}, R2 {int((run == 'R2').sum())}) | LAT {LAT} ms exit {EX} | base mean {V.mean():+.4f}/launch, fills {fill.mean():.0%}")
for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
    idx = np.where(run == tr_run)[0]; cut = idx[int(len(idx) * 0.8)]
    TR = (run == tr_run) & (np.arange(len(rows)) < cut) & guard; VA = (run == tr_run) & (np.arange(len(rows)) >= cut) & guard; TE = (run == te_run) & guard
    Bm = G.binize(X, TR)
    trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
    acc = np.zeros(len(FK))
    for t in trees: G.imp(t, acc)
    print(f"\ntrain {tr_run} -> test {te_run}: trees {len(trees)} AUC val {G.auc(y[VA], f[VA]):.3f} test {G.auc(y[TE], f[TE]):.3f} | top: " + ", ".join(f"{FK[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:6]))
    for q in (0.005, 0.01, 0.02, 0.05):
        thr = np.quantile(f[VA], 1 - q); st = TE & (f >= thr)
        print(f"   ours top {q:5.1%}: n {st.sum():4d} fills {fill[st].sum():4d} total {V[st].sum():+6.2f} mean {V[st].mean() if st.sum() else 0:+.4f} | w/o best 5 {np.sort(V[st])[:-5].sum() if st.sum() > 5 else 0:+6.2f}")
    sf = TE & f2
    print(f"   FINAL-2 picks : n {sf.sum():4d} fills {fill[sf].sum():4d} total {V[sf].sum():+6.2f} mean {V[sf].mean() if sf.sum() else 0:+.4f} | w/o best 5 {np.sort(V[sf])[:-5].sum() if sf.sum() > 5 else 0:+6.2f}" + ("   (in-sample for FINAL-2)" if te_run == "R1" else ""))
