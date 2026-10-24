#!/usr/bin/env python3
# Which big-sell dips are worth buying? GBDT on dip events (events_lc120tp.jsonl.gz: sells >= 1 SOL at age 1-120 s, low cost
# 0.0008 SOL/tx, no fill penalty), label = round-trip PnL > 0 for entry ENT and exit EXIT. Train on one run (early stop on its
# last 20%), test on the other run; both directions. Reports top-k% by score: n, mean PnL, win, total; plus a cost-stress column.
import sys, os, json, gzip, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbdt_np as G
ENT = os.environ.get("ENT", "E1"); EXIT = os.environ.get("EXIT", "tp1.05_sl0.0_h30")
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
W = json.load(open("/home/moiz/sniper/ops/overnight/core/gf_wallets.json"))
SN8 = {u[:8] for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
R = [json.loads(l) for l in gzip.open(os.environ.get("EVF", "/home/moiz/sniper/ops/overnight/dip/events_lc120tp.jsonl.gz"), "rt")]
R = [r for r in R if ENT in r["pnl"] and EXIT in r["pnl"][ENT]]
R.sort(key=lambda r: (r["bt"], r["age"]))
XF = ["s_frac", "s_pnl", "s_nb", "s_entry", "s_in_bundle", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow"]
FK = ["age", "sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "pro_seller", "snp_seller", "sell_share", "bs_ratio"] + (XF if os.environ.get("XF") else []) + (["px_ent"] if os.environ.get("PXENT") else [])   # px_ent is NOT causal (uses trades after our decision): off by default
def fv(r):
    d = dict(r); d["first_big"] = float(r["first_big"]); d["ins"] = float(r["ins"]); d["pro_seller"] = float(r["seller"].startswith(PRO6)); d["snp_seller"] = float(r["seller"] in SN8)
    d["sell_share"] = r["sell"] / max(r["vsol"] - 30, 0.1); d["bs_ratio"] = r["b20"] / (r["s20"] + 0.1); d.update(r.get("xf", {})); d["px_ent"] = r.get("px_" + ENT, 1.0) if "px_" + ENT in r else (r.get("px", {}).get(ENT, 1.0))
    return [float(d[k]) for k in FK]
X = np.array([fv(r) for r in R]); P = np.array([r["pnl"][ENT][EXIT] for r in R]); y = (P > 0).astype(float)
run = np.array([r["run"] for r in R])
print(f"events {len(R)} | entry {ENT} exit {EXIT} | base mean {P.mean():+.4f} win {y.mean():.0%}")
for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
    idx = np.where(run == tr_run)[0]; cut = idx[int(len(idx) * 0.8)]
    TR = (run == tr_run) & (np.arange(len(R)) < cut); VA = (run == tr_run) & (np.arange(len(R)) >= cut); TE = run == te_run
    Bm = G.binize(X, TR)
    trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
    acc = np.zeros(len(FK))
    for t in trees: G.imp(t, acc)
    print(f"\ntrain {tr_run} -> test {te_run}: trees {len(trees)} AUC val {G.auc(y[VA], f[VA]):.3f} test {G.auc(y[TE], f[TE]):.3f} | top features: " +
          ", ".join(f"{FK[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:6]))
    if os.environ.get("SAVE"):
        sv_rows = [dict(m=R[i]["m"], bt=R[i]["bt"], age=R[i]["age"], run=R[i]["run"], score=float(f[i]), thr2=float(np.quantile(f[VA], 0.98)), thr5=float(np.quantile(f[VA], 0.95)),
                        pnl=R[i]["pnl"][ENT]) for i in np.where(TE)[0]]
        json.dump(sv_rows, open(f"/home/moiz/sniper/ops/overnight/dip/sel{os.environ.get('SFX', '')}_{ENT}_{EXIT}_{tr_run}to{te_run}.json", "w"))
    for q in (0.01, 0.02, 0.05, 0.10, 0.20):
        thr = np.quantile(f[VA], 1 - q); sv = VA & (f >= thr); st = TE & (f >= thr)
        if st.sum() == 0: continue
        print(f"   top {q:4.0%}: val n {sv.sum():4d} mean {P[sv].mean():+.4f} | TEST n {st.sum():5d} mean {P[st].mean():+.4f} win {(P[st] > 0).mean():.0%} total {P[st].sum():+7.2f} | +0.002/tx cost: {P[st].mean() - 0.004:+.4f}")
