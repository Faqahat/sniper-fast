#!/usr/bin/env python3
"""BOTREG step 7 [MEASURED, DEV out-of-fold only, comparison]: FP-NOBOT's frozen recipe (gbm_s, all inputs minus a_spend,
leave-one-block-out B1 r37-41 | B2 r42 | B3 r43-48 | B4 r49-54, 3 seeds, threshold = train-OOF quantile) re-run with the
bot inputs from a different follower list. Code = flatperfect x8_variants.cv / x11_cvfinal.py logic, copied (not imported,
because x8 builds its label from dev_chain.pkl at import).
usage: x7_fpnobot_cv.py FEAT_PKL LABEL_PKL NAME"""
import sys, pickle, warnings
warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/flatperfect")
import numpy as np, lightgbm as lgb
import ftab
feat_pkl, lab_pkl, name = sys.argv[1], sys.argv[2], sys.argv[3]
P, cols, X = ftab.table(feat_pkl)
_, lcols, LX = ftab.table(lab_pkl)
ci = {c: i for i, c in enumerate(cols)}
lab = LX[:, {c: i for i, c in enumerate(lcols)}["L_bot2"]]


def q3a(p):
    if p["kind"] != "T2": return False
    v, q = p.get("v2") or {}, p.get("quiet") or {}
    n, wd = v.get("n_120s"), q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n <= 15 and wd <= 3


assert not any(p["run"] == "r55" for p in P)
BL = {"r37": 1, "r38": 1, "r39": 1, "r40": 1, "r41": 1, "r42": 2}
blk = np.array([BL.get(p["run"], 3 if p["run"] <= "r48" else 4) for p in P])
DROP = {"o_n", "o_run_min", "v_ring", "wh_age", "cov"}
pn = np.array([p["pnl"] for p in P]); cl = np.array([p["cls"] for p in P]); kd = np.array([p["kind"] for p in P])
y = (lab == 0).astype(int)
ELIG = np.array([not q3a(p) for p in P]) & ~np.isnan(lab)
FE = [c for c in cols if not c.startswith("L_") and c not in DROP and c != "a_spend"]


def mk(seed):
    return lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=4, min_child_samples=60, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, reg_lambda=10, verbose=-1, random_state=seed)


def fitpred(Xtr, ytr, Xte, seeds=(0, 1, 2)):
    return np.mean([mk(s).fit(Xtr, ytr).predict_proba(Xte)[:, 1] for s in seeds], 0)


def cv(feats, kinds, qs=(0.1, 0.15, 0.2, 0.25)):
    fj = [ci[c] for c in feats]; out = {}
    for kind in kinds:
        res = {q: [] for q in qs}
        for b in (1, 2, 3, 4):
            trm = ELIG & (blk != b) & (kd == kind); tem = ELIG & (blk == b) & (kd == kind)
            Xa = X[:, fj]
            s = fitpred(Xa[trm], y[trm], Xa)
            idx = np.nonzero(trm)[0]; oof = np.empty(len(idx)); h = len(idx) // 2
            for a, bb in ((idx[:h], idx[h:]), (idx[h:], idx[:h])):
                oof[np.searchsorted(idx, bb)] = fitpred(Xa[a], y[a], Xa[bb], seeds=(0,))
            for q in qs:
                t = np.quantile(oof, 1 - q); B = tem & (s >= t); sv = -pn[B]
                res[q].append((B.sum(), (cl[B] == "flat").sum(), (cl[B] == "win").sum(), pn[B & (cl == "win")].sum(), sv.sum(),
                               sv.sum() - np.sort(sv)[::-1][:5].sum()))
        out[kind] = res
    return out


o = cv(FE, ("T2", "rearm"))
for kind, res in o.items():
    line = []
    for q, r in res.items():
        line.append(f"q{q:.2f}: n{sum(x[0] for x in r)} fl{sum(x[1] for x in r)} w{sum(x[2] for x in r)}({sum(x[3] for x in r):+.2f}) "
                    f"sv{sum(x[4] for x in r):+.2f} w/o5 {sum(x[5] for x in r):+.2f} pos{sum(x[4] > 0 for x in r)}/4 w5pos{sum(x[5] >= 0 for x in r)}/4")
    print(f"{name:28s} {kind:5s} | " + " | ".join(line), flush=True)
