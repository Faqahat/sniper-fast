#!/usr/bin/env python3
# Later-entry (no race) model: per decision time T, a histogram GBDT (ops/select/e_model.py code) on the features
# known at T (gf_points.jsonl.gz), label = return > 0 at exit EX. Train on one period (first 80%, early stop on the last
# 20%), test on the OTHER period; both directions. Cut = top-k of the validation scores, applied unchanged to the test.
# Also reports the test result with every sniper/pro buy after our entry removed (nosnip).
# usage: python3 -I gf_model.py
import json, gzip, sys
import numpy as np
CORE = "/home/moiz/sniper/ops/overnight/core"
src = open("/home/moiz/sniper/ops/select/e_model.py").read(); exec(src[src.index("def binize"):src.index("def stats")])
P = [json.loads(l) for l in gzip.open(f"{CORE}/gf_points.jsonl.gz", "rt")]
FK = list(P[0]["f"].keys())
def fv(p): return [p["f"][k] for k in FK] + [p["dev"], p["gl"], p["gls"], p["mcb"], p["hr"]] + p["rec"]
TS = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "3,5,8,12,20,30,60").split(",")]
EXS = (sys.argv[2] if len(sys.argv) > 2 else "h30,h60,h120,tp1.5_sl.8_c300,tp2_sl.75_c300,tr1.15_12_c180").split(",")
res = []
for T in TS:
    rows = [p for p in P if p["T"] == T]
    rows.sort(key=lambda p: (p["run"], p["m"]))
    X = np.array([fv(p) for p in rows], float); run = np.array([p["run"] for p in rows])
    for ex in EXS:
        ok = np.array([not p["o"][ex][2] for p in rows]); y_ret = np.array([p["o"][ex][0] for p in rows])
        y_ns = np.array([p["o"][ex][1] if p["o"][ex][1] is not None else p["o"][ex][0] for p in rows]); y = (y_ret > 0).astype(float)
        for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
            idx_tr = np.where((run == tr_run) & ok)[0]; cut = int(len(idx_tr) * 0.8)
            rng = np.random.default_rng(0); perm = rng.permutation(idx_tr)        # random 80/20 split inside the training period
            TR = np.zeros(len(rows), bool); VA = np.zeros(len(rows), bool); TR[perm[:cut]] = True; VA[perm[cut:]] = True
            TE = (run == te_run) & ok
            Bm = binize(X, TR); trees, f = fit(Bm, y, TR, VA, rounds=300, lr=0.05, depth=3)
            for q in (0.98, 0.95, 0.9):
                c = np.quantile(f[VA], q); s = TE & (f >= c)
                if s.sum() < 5: continue
                res.append(dict(T=T, ex=ex, train=tr_run, top=round(1 - q, 2), n=int(s.sum()), mean=float(y_ret[s].mean()), med=float(np.median(y_ret[s])),
                                win=float((y_ret[s] > 0).mean()), tot=float(y_ret[s].sum() * 0.5), tot_ns=float(y_ns[s].sum() * 0.5),
                                wo5=float((y_ret[s].sum() - np.sort(y_ret[s])[-5:].sum()) * 0.5), auc=auc(y[TE], f[TE]), base=float(y_ret[TE].mean())))
json.dump(res, open(f"{CORE}/gf_model_res.json", "w"))
print("test-period results (model trained on the other period); 0.5 SOL per trade")
print(" T   exit             train  top   n    mean%   med%   win   total  w/o-top5  nosnip-total  AUC   (base mean% of all test points)")
for r in sorted(res, key=lambda r: (r["T"], r["ex"], r["top"], r["train"])):
    print(f"{r['T']:3d}  {r['ex']:16s} {r['train']}->  {r['top']:.2f} {r['n']:4d}  {r['mean']*100:+6.2f} {r['med']*100:+6.2f}  {r['win']:.2f} {r['tot']:+7.2f} {r['wo5']:+7.2f}  {r['tot_ns']:+7.2f}   {r['auc']:.3f}  ({r['base']*100:+.2f})")
both = {}
for r in res: both.setdefault((r["T"], r["ex"], r["top"]), {})[r["train"]] = r
print("\npositive in BOTH directions (train R1->test R2 and train R2->test R1):")
for k, v in sorted(both.items()):
    if len(v) == 2 and all(x["tot"] > 0 for x in v.values()):
        a, b = v["R1"], v["R2"]
        print(f"  T={k[0]:3d} {k[1]:16s} top {k[2]:.2f}: test R2 {a['tot']:+.2f} (n {a['n']}, w/o top5 {a['wo5']:+.2f}, nosnip {a['tot_ns']:+.2f}) | test R1 {b['tot']:+.2f} (n {b['n']}, w/o top5 {b['wo5']:+.2f}, nosnip {b['tot_ns']:+.2f})")
