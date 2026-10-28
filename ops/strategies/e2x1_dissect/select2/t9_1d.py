#!/usr/bin/env python3
"""select2 t9: one-feature rules (human-readable) on TEST: for each feature and threshold, recall of his picks, precision, and the
66 ms sim P&L (34 s exit, phi 0.2 and 0) + g94 of rule-only picks (not his) vs his. Universe rows: samp|y, Grozoe-trigger rows dropped."""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
U = dict(np.load(f"{OUT}/U2.npz")); S = dict(np.load(f"{OUT}/sim_66.npz"))
y = U["y"].astype(bool); samp = U["samp"].astype(bool); rows = (samp | y) & (U["u_is_sib"] == 0); wt = np.where(y, 1.0, 25.0)
TE = (U["bt"] >= U["bt"].max() - 86400) & rows; TR = rows & ~TE
def ev(sel, te=TE):
    r = {}
    for g, m in (("his", sel & y & te), ("not_his", sel & ~y & te), ("missed", ~sel & y & te)):
        w = wt[m]; r[g] = dict(n=int(m.sum()), g94=float(100 * np.average(np.clip(U["g94"][m], -1, 5), weights=w)) if m.any() else None,
                              sim34_phi02=float(1000 * np.average(S["tier|34s|0.2|pnl"][m], weights=w)) if m.any() else None,
                              sim34_phi0=float(1000 * np.average(S["tier|34s|0.0|pnl"][m], weights=w)) if m.any() else None,
                              sim5_phi0=float(1000 * np.average(S["tier|5s|0.0|pnl"][m], weights=w)) if m.any() else None,
                              fill=float(np.average(S["tier|34s|0.2|fill"][m], weights=w)) if m.any() else None)
    r["recall"] = float((sel & y & te).sum() / (y & te).sum()); r["prec"] = float((sel & y & te).sum() / max(wt[sel & te].sum(), 1)); r["picks_day"] = float(wt[sel & te].sum())
    return r
out = {}
CAND = {"u_follow_rate_sm": [0.003, 0.005, 0.01, 0.02, 0.05], "u_follow_n": [1, 3, 5, 10, 20], "u_cw541": [1], "u_trips": [50, 200, 1000], "u_ret_per_sol": [0.0, 0.02, 0.05],
        "u_census_tot": [1, 10], "n_cw_in": [5, 10, 20], "n_follow_in": [1, 3, 5], "cop_buys": [1], "my_buys": [1], "tx_cup": [500000, 1000000, 5000000], "tx_f_routed": [1],
        "cr_prev": [1, 5], "dev_buy0": [0.5, 1, 2], "solin_cur": [0.5, 1, 2, 5], "solin_1s": [1, 2, 5], "sol": [0.5, 1, 2], "age_s": [10, 30, 120]}
for f, ths in CAND.items():
    for t in ths:
        for op in (">=", "<"):
            sel = (U[f] >= t) if op == ">=" else (U[f] < t)
            r = ev(sel & rows); r["train"] = ev(sel & rows, TR); out[f"{f} {op} {t}"] = r
            print(f"{f:18s} {op} {t:>8}: recall {r['recall']:.2f} prec {r['prec']:.4f} picks/day {r['picks_day']:8.0f} | his sim34(0.2) {r['his']['sim34_phi02']} not-his {r['not_his']['sim34_phi02']} (phi0 {r['not_his']['sim34_phi0']}) g94 {r['not_his']['g94']} n_not_his {r['not_his']['n']} | train not-his sim34 {r['train']['not_his']['sim34_phi02']}")
json.dump(out, open(f"{OUT}/t9.json", "w"), indent=1)
