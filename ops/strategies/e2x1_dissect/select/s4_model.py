#!/usr/bin/env python3
"""SELECT s4: does a market-feature model reproduce which trade events E2x1 reacts to? Time split: TEST = newest 6 h of the tape
(10-28 12:41 -> 18:41 PKT, never used for choices), VAL = the 12 h before (early stop), TRAIN = the rest.
Rows = positives + the 4 % hash sample of negatives (uniform -> AUC unbiased). GBDT (numpy) logistic.
Reports AUC, precision/recall at top-k, lift, importance; saves OOS scores for the test part."""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); import dd_gbdt as G
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
U = dict(np.load(f"{OUT}/U.npz"))
MKT = ["age_s", "vsol", "is_buy", "sol", "imp", "by_creator", "ret_1s", "ret_5s", "ret_30s", "ret_120s", "dd_peak", "mult", "peak_mult",
       "nb_cur", "ns_cur", "solin_cur", "solout_cur", "nb_1s", "ns_1s", "solin_1s", "solout_1s", "nb_5s", "ns_5s", "solin_5s", "solout_5s",
       "nb_30s", "ns_30s", "solin_30s", "solout_30s", "ntr", "nusers", "dev_sells", "dev_buy_sol", "tot_in", "bundle_sol", "gap_prev_sl",
       "user_ntr", "cr_prev", "hour"]
OWN = ["my_buys", "my_open"]
def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
def run(feats, ylab, tag, rows_extra=None):
    y = U[ylab].astype(bool)
    rows = U["samp"] | y
    if rows_extra is not None: rows &= rows_extra
    X = np.column_stack([U[f].astype(np.float64) for f in feats])[rows]; yy = y[rows].astype(float); bt = U["bt"][rows]
    tmax = U["bt"].max(); te = bt >= tmax - 6 * 3600; va = (bt >= tmax - 18 * 3600) & ~te; tr = ~te & ~va
    E = G.edges_of(X, tr); B = G.binize(X, E)
    M = G.fit(B, yy, tr, va, loss="log", rounds=600, lr=0.08, depth=4, min_n=200, lam=5.0, seed=1)
    s = G.predict(M, B)
    res = dict(tag=tag, n_tr=int(tr.sum()), pos_tr=int(yy[tr].sum()), n_te=int(te.sum()), pos_te=int(yy[te].sum()),
               auc_va=auc(s[va], yy[va] > 0), auc_te=auc(s[te], yy[te] > 0), rounds=M["best_round"])
    # precision at top fractions of test, as lift over base rate (negatives weighted x25)
    st, yt = s[te], yy[te] > 0; o = np.argsort(-st); wts = np.where(yt, 1.0, 25.0)[o]; cy = np.cumsum(yt[o]); cw = np.cumsum(wts)
    base = yt.sum() / wts.sum(); out = []
    for rec in (0.1, 0.25, 0.5, 0.75):
        k = np.searchsorted(cy, rec * yt.sum()); out.append((rec, float(cy[k] / cw[k]), float(cy[k] / cw[k] / base)))
    res["prec_at_recall"] = out; res["base_rate"] = float(base)
    imp = G.importance(M, len(feats)); res["imp"] = sorted(zip(feats, imp.round(3).tolist()), key=lambda z: -z[1])[:15]
    print(json.dumps(res), flush=True)
    return s, rows, te
if __name__ == "__main__":
    s, rows, te = run(MKT, "y", "MKT y")
    np.savez(f"{OUT}/s4_scores.npz", s=s, rows=np.flatnonzero(rows), te=te)
    run(MKT + OWN, "y", "MKT+OWN y")
    run(MKT, "yfirst", "MKT yfirst", rows_extra=(U["my_buys"] == 0))
