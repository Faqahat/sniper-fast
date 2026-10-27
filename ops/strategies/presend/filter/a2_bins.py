#!/usr/bin/env python3
"""PRESEND FILTER, analysis 2 (DEV ONLY): net by feature bins (quantiles), mid-rank AUC, for the filled windows; and the arm-level
value (fill net - the window's failed-try fees) for ALL windows (an ARM skip also saves the unfilled windows' fees)."""
import json, sys
import numpy as np
B = "/home/moiz/sniper-data/presend_filter"
W = [w for w in json.load(open(f"{B}/windows.json")) if w["run"] in ("ams:r24", "ams:r25") and w["chain_ok"]]


def auc(xw, xl):
    allx = np.r_[xw, xl]
    order = np.argsort(allx, kind="mergesort"); ranks = np.empty(len(allx))
    sx = allx[order]; i = 0
    while i < len(sx):
        j = i
        while j + 1 < len(sx) and sx[j + 1] == sx[i]: j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1; i = j + 1
    return (ranks[:len(xw)].sum() - len(xw) * (len(xw) + 1) / 2) / (len(xw) * len(xl))


def val(w): return ((w["net"] if w["filled"] else 0) - w["fail_fee"]) / 1e9


feats = sys.argv[1:] or ["age", "n_tr", "n_users", "vol", "n_tr_50", "cre_prev", "dev_sold", "dev_hold", "wh_nf", "wh_bounce", "wh_fill", "wh_n", "wh_tokens_before",
                         "wh_first_age", "coh_n", "coh_hold", "fb_n", "fb_hold", "n_big", "top10", "pct", "whale_sol", "vsol", "trig_tip", "trig_cup", "tok_dumps", "oc_depth",
                         "slots_after_trigger", "p_ret_20", "dd_peak", "since_last", "n_tr_10", "vol_10"]
F = [w for w in W if w["filled"]]
for k in feats:
    x = np.array([float(w[k]) if w.get(k) is not None else np.nan for w in F]); y = np.array([w["net"] > 0 for w in F]); net = np.array([w["net"] for w in F]) / 1e9
    nt = np.array([w.get("y_nb") == 0 for w in F])
    ok = ~np.isnan(x)
    a = auc(x[ok & y], x[ok & ~y])
    qs = np.unique(np.nanpercentile(x, [0, 20, 40, 60, 80, 100]))
    line = f"{k:18s} AUC {a:.2f} |"
    xa = np.array([float(w[k]) if w.get(k) is not None else np.nan for w in W]); va = np.array([val(w) for w in W]); fa = np.array([w["filled"] for w in W])
    for lo, hi in zip(qs[:-1], qs[1:]):
        m = ok & (x >= lo) & ((x < hi) if hi < qs[-1] else (x <= hi))
        ma = (xa >= lo) & ((xa < hi) if hi < qs[-1] else (xa <= hi))
        line += f" [{lo:.3g},{hi:.3g}] f{m.sum()} w{(m & y).sum()} nt{(m & nt).sum()} {net[m].sum():+.2f} arm{va[ma].sum():+.2f}/{ma.sum()} |"
    print(line)
