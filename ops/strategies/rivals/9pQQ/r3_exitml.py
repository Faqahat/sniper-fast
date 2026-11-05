#!/usr/bin/env python3
"""9pQQ learned exit (T3b).  A GBDT learns, from the state after each outside trade during its holds, whether 9pQQ sells next
(10-28 + 10-30 train).  Policy for US: on its picks, entered DELTA ms after the trade it reacted to, sell DELTA ms after the first
outside trade whose score > theta (theta chosen on 10-31), else at 2,800 slots.  Final check 11-02.  Compared with its real exit.
Features (all visible on chain at that moment): slots held, return vs entry, drawdown from peak, side, size, slots since previous
outside buy, net flow 10 slots, net flow since entry, trader's trade count, seller had bought during the hold, share of follower
tokens sold, distinct sellers, slots since previous outside sell.  -> exitml.json.  Read-only.  usage: r3_exitml.py [DELTA]"""
import sys, pickle, json
import numpy as np
import tlib9 as L, rlib9 as R, gbdt_np as G
from a3_clusters import label

D = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
FC = [1, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16]
NAMES = ["slots", "ret", "dd", "side", "size", "since_buy", "flow10", "flow_entry", "trader_cnt", "follower_sell", "fol_sold_frac", "n_sellers", "since_sell"]
Z = {r: np.load(f"{L.OUT}/exits_{r}.npy") for r in L.RUNS}
X = np.concatenate([Z[r][:, FC] for r in L.RUNS]); run_ix = np.concatenate([np.full(len(Z[r]), k) for k, r in enumerate(L.RUNS)])
y = np.concatenate([((Z[r][:, 7] == 1) & (Z[r][:, 8] <= 1) & (Z[r][:, 17] == 0)).astype(float) for r in L.RUNS])
during = np.concatenate([Z[r][:, 17] == 0 for r in L.RUNS])
tr = (run_ix <= 1) & during; va = (run_ix == 2) & during
B = G.binize(X, tr)
trees, f = G.fit(B, y, tr, va, rounds=300, lr=0.08, depth=4)
p = 1 / (1 + np.exp(-f))
imp = np.zeros(len(FC)); [G.imp(t_, imp) for t_ in trees]
out = {"delta_ms": D, "auc_train": G.auc(y[tr], p[tr]), "auc_10-31": G.auc(y[va], p[va]),
       "auc_11-02": G.auc(y[(run_ix == 3) & during], p[(run_ix == 3) & during]),
       "importance": sorted(zip(NAMES, (imp / imp.sum()).round(3).tolist()), key=lambda z: -z[1])}
print(json.dumps(out), flush=True)
THS = (0.02, 0.03, 0.05, 0.08, 0.12, 0.2)
res = {}
off = 0
for k, r in enumerate(L.RUNS):
    a = Z[r]; pr = p[off:off + len(a)]; off += len(a)
    t = L.load_tape(r); wid = t.user_ix[L.W]; s0, bsz = R.blocksizes(r)
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x["net"] is not None and x.get("tape_ok")]
    tn = a[:, 0].astype(int); order = np.argsort(tn, kind="stable"); starts = np.searchsorted(tn[order], np.arange(len(T) + 1))
    rcc = a[:, 18] * R.SMS + a[:, 19] / np.maximum(bsz[np.clip(a[:, 18].astype(int) - s0, 0, len(bsz) - 1)], a[:, 19] + 1) * R.SMS
    rows = {th: [] for th in THS}; its = []; labs = []; cache = {}
    for n, x in enumerate(T):
        mi = t.mint_ix[x["mint"]]
        M = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = M
        key = M.S * 10000 + M.I
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        if js >= len(M.S) or M.U[js] != wid or M.U[jb] != wid: continue
        j = jb - 1
        while j >= 0 and M.U[j] == wid: j -= 1
        ti = (M.CC[j] if j >= 0 else M.CC[jb]) + D
        ix = order[starts[n]:starts[n + 1]]
        its.append(R.trip(M, ti, M.CC[js] + max(0.0, D - 45), drop9=True)); labs.append(label(x)[0])
        cap = (x["bs"] + 2800) * R.SMS
        for th in THS:
            q = ix[(pr[ix] > th) & (rcc[ix] >= ti)]
            dec = rcc[q[0]] if len(q) else cap
            rows[th].append(R.trip(M, ti, dec + D, drop9=True))
    res[L.DAY[r]] = dict(its=np.array(its) / 1e9, lab=np.array(labs), **{str(th): np.array(v) / 1e9 for th, v in rows.items()})
pick = max(THS, key=lambda th: res["10-31"][str(th)].sum())
out["theta_picked_on_10-31"] = pick
for day, d in res.items():
    o = {}
    for k in ["its"] + [str(th) for th in THS]:
        v = np.sort(d[k]); o[k] = dict(net=round(v.sum(), 2), msol=round(1000 * v.mean(), 2), wo_top5=round(v[:-5].sum(), 2))
    for lab in ("LAUNCH", "DIP", "MOMO", "DRIFT"):
        m = d["lab"] == lab
        for k in ("its", str(pick)):
            v = np.sort(d[k][m]); o[f"{lab} {k}"] = dict(n=int(m.sum()), net=round(v.sum(), 2), msol=round(1000 * v.mean(), 2), wo_top5=round(v[:-5].sum(), 2))
    out[day] = o
    print(day, json.dumps(o), flush=True)
json.dump(out, open(f"/home/moiz/sniper/ops/strategies/rivals/9pQQ/exitml_{int(D)}.json", "w"), indent=1)
