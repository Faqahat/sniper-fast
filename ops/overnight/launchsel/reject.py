#!/usr/bin/env python3
# REJECT filters: AND-rules (<= 3 conditions) whose picks are mostly instant dumps / dead launches, found on TRAIN, precision on TEST.
import json, gzip, time, calendar
import numpy as np
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/launchsel/launches.jsonl.gz", "rt")]
SPLIT = calendar.timegm(time.strptime("2026-10-23 06:00", "%Y-%m-%d %H:%M")) - 18000
F0 = ["dev_buy", "create_fee", "prior_creates", "prior_n", "cr_prev", "cr_grad", "has_funder", "fu_prev", "tw", "tg", "web", "desc_len", "name_len", "meta_ok"]
F1 = F0 + ["bundle_n", "ins_n", "jito", "ins_sold", "dev_sold", "n_buys", "n_sells", "uniq_out", "out_sol", "buy_sol", "sell_sol", "net", "top_share", "max_buy", "vsol", "chg", "dd", "coh_n", "slot01_out", "since_last"]
for d, feats in ((0, F0), (1, F1), (3, F1)):
    V = [r for r in R if r["d"] == d]; T = np.array([r["bt"] for r in V]); tr = T < SPLIT; te = ~tr
    for target in ("dump", "dead", "bad"):
        y = np.array([(r["dump"] or r["dead"]) if target == "bad" else r[target] for r in V]).astype(bool)
        loss = np.array([r["res"]["h30s"] for r in V])
        X = np.array([[float(r.get(k) or 0) for k in feats] for r in V])
        best = []
        for j, k in enumerate(feats):
            for q in np.linspace(0.05, 0.95, 19):
                v = float(np.quantile(X[tr, j], q))
                for op in (">=", "<="):
                    m = (X[:, j] >= v) if op == ">=" else (X[:, j] <= v)
                    if (m & tr).sum() < 0.05 * tr.sum(): continue
                    best.append((y[m & tr].mean(), k, op, v, m))
        best.sort(key=lambda x: -x[0])
        print(f"\nREJECT d={d}s target={target}: base TRAIN {y[tr].mean():.1%} TEST {y[te].mean():.1%}")
        for p, k, op, v, m in best[:5]:
            print(f"   {k} {op} {v:.4g}: TRAIN precision {p:.1%} | TEST precision {y[m & te].mean():.1%}, removes {m[te].mean():.0%} of launches, their 30 s P&L {loss[m & te].sum():+.1f} vs kept {loss[~m & te].sum():+.1f}")
