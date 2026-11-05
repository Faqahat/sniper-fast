#!/usr/bin/env python3
"""FLATPERFECT step 5: train + FREEZE the flat filter 'FP-NOBOT' on DEV runs r37..r54 only (r55 never loaded).
Target  : nobot = no cohort/named follower-bot buy within 2 slots after our fill (L_bot2 == 0), the mechanism behind flats.
Model   : per kind (T2 / re-arm) LightGBM (num_leaves 4, 200 trees, lr .03, min_child 60, L2 10), mean of seeds 0,1,2.
Data    : eligible DEV positions = QUIET3-A T2 removed (live in r55), chain-covered (label + chain features exist).
Features: all causal fp1 (chain at trigger + pre-fill <= fill-2) + fp2 (arm record + own recent outcomes) columns, minus run-identity ones.
Block   : score >= thr, thr = (1-q) quantile of 2-fold time-halves OOF scores (seed 0) = exactly the CV scheme; q T2 0.15, re-arm 0.20.
          A position without chain coverage is never blocked.
Writes  : models + FROZEN_FLAT.json (+ dev OOF per-run table)."""
import sys, os, json, hashlib, pickle, datetime, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np, lightgbm as lgb
import ftab, base
HERE = "/home/moiz/sniper/ops/strategies/presend/flatperfect"
OUTD = "/home/moiz/sniper-data/flatperfect"
DEVCHAIN = os.environ.get("DEVCHAIN", f"{OUTD}/dev_chain_full.pkl")
DROP = {"o_n", "o_run_min", "v_ring", "wh_age", "cov", "a_spend"}
Q = {"T2": 0.15, "rearm": 0.20}
SEEDS = (0, 1, 2)
PRM = dict(n_estimators=200, learning_rate=0.03, num_leaves=4, min_child_samples=60, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
           reg_lambda=10, verbose=-1)
BL = {"r37": 1, "r38": 1, "r39": 1, "r40": 1, "r41": 1, "r42": 2}
COST = 0.017


def q3a(p):
    if p["kind"] != "T2": return False
    v, q = p.get("v2") or {}, p.get("quiet") or {}
    n, wd = v.get("n_120s"), q.get("wh_dumps")
    return n is not None and wd is not None and q.get("rule_on") is not False and n <= 15 and wd <= 3


def sha(fn): return hashlib.sha256(open(fn, "rb").read()).hexdigest()


def fitpred(Xtr, ytr, Xte, seeds=SEEDS):
    return np.mean([lgb.LGBMClassifier(**PRM, random_state=s).fit(Xtr, ytr).predict_proba(Xte)[:, 1] for s in seeds], 0)


def f20(x):
    g = x + COST
    return 0.8 * g - COST if g > 0 else x


if __name__ == "__main__":
    P, cols, X = ftab.table(DEVCHAIN)
    assert not any(p["run"] == "r55" for p in P)
    ci = {c: i for i, c in enumerate(cols)}
    FEATS = [c for c in cols if not c.startswith("L_") and c not in DROP]
    fj = [ci[c] for c in FEATS]
    lab = X[:, ci["L_bot2"]]; y = (lab == 0).astype(int)
    pn = np.array([p["pnl"] for p in P]); cl = np.array([p["cls"] for p in P]); kd = np.array([p["kind"] for p in P])
    blk = np.array([BL.get(p["run"], 3 if p["run"] <= "r48" else 4) for p in P])
    el = np.array([not q3a(p) for p in P]) & ~np.isnan(lab)
    frozen = {"name": "FP-NOBOT", "written_pkt": datetime.datetime.now(base.PKT).strftime("%Y-%m-%d %H:%M:%S"),
              "train": "DEV r37..r54 eligible (QUIET3-A T2 removed) chain-covered positions; r55 never loaded",
              "target": "L_bot2 == 0 (no cohort/named follower buy <= 2 slots after our fill)", "params": PRM, "seeds": SEEDS,
              "features": FEATS, "drop": sorted(DROP), "q": Q, "kinds": {}, "cost_f20": COST,
              "rule": "block iff chain-covered and mean-seed score >= thr[kind]; else pass"}
    dev_oof = np.full(len(P), np.nan)
    for kind in ("T2", "rearm"):
        m = el & (kd == kind)
        idx = np.nonzero(m)[0]
        Xa = X[:, fj]
        files = []
        for s in SEEDS:
            mod = lgb.LGBMClassifier(**PRM, random_state=s).fit(Xa[idx], y[idx])
            fn = f"{OUTD}/frozen_{kind}_s{s}.txt"; mod.booster_.save_model(fn); files.append(fn)
        h = len(idx) // 2; oof = np.empty(len(idx))
        for a, b in ((idx[:h], idx[h:]), (idx[h:], idx[:h])):
            oof[np.searchsorted(idx, b)] = fitpred(Xa[a], y[a], Xa[b], seeds=(0,))
        thr = float(np.quantile(oof, 1 - Q[kind]))
        # honest DEV per-run view: leave-one-block-out scores (models trained without that block, thr from their own train halves)
        for b in (1, 2, 3, 4):
            tr = m & (blk != b); te = m & (blk == b)
            ii = np.nonzero(tr)[0]; hh = len(ii) // 2; o2 = np.empty(len(ii))
            for a_, b_ in ((ii[:hh], ii[hh:]), (ii[hh:], ii[:hh])):
                o2[np.searchsorted(ii, b_)] = fitpred(Xa[a_], y[a_], Xa[b_], seeds=(0,))
            t_b = np.quantile(o2, 1 - Q[kind])
            sc = fitpred(Xa[tr], y[tr], Xa[te])
            dev_oof[np.nonzero(te)[0]] = (sc >= t_b).astype(float)
        frozen["kinds"][kind] = {"thr": thr, "n_train": int(len(idx)), "nobot_rate": float(y[idx].mean()),
                                 "models": {os.path.basename(f): sha(f) for f in files}}
        print(kind, "train", len(idx), "thr", round(thr, 4), flush=True)
    # DEV per-run table (leave-one-block-out decisions)
    rows = collections.OrderedDict()
    for i, p in enumerate(P):
        if not el[i]: continue
        r = rows.setdefault((p["run"], p["kind"]), [])
        r.append((p["pnl"], p["cls"], dev_oof[i] == 1))
    tab = []
    for (run, kind), v in rows.items():
        b = [x for x in v if x[2]]
        sv = sorted([-x[0] for x in b], reverse=True)
        tab.append({"run": run, "kind": kind, "n": len(v), "flats_all": sum(x[1] == "flat" for x in v),
                    "blocked": len(b), "flats": sum(x[1] == "flat" for x in b), "flat_sol": round(sum(x[0] for x in b if x[1] == "flat"), 3),
                    "wins": sum(x[1] == "win" for x in b), "win_sol": round(sum(x[0] for x in b if x[1] == "win"), 3),
                    "smalls": sum(x[1] == "small" for x in b), "small_sol": round(sum(x[0] for x in b if x[1] == "small"), 3),
                    "bigl": sum(x[1] == "bigloss" for x in b), "bigl_sol": round(sum(x[0] for x in b if x[1] == "bigloss"), 3),
                    "saved": round(sum(sv), 3), "wo5": round(sum(sv[5:]), 3), "f20": round(-sum(f20(x[0]) for x in b), 3)})
    json.dump(tab, open(f"{OUTD}/dev_oof_runs.json", "w"), indent=0)
    code = ["base.py", "ftab.py", "fp_f2_runs.py", "fp1_chain.py", "fp2_own.py", "fp4_chain_extend.py", "fp5_freeze.py", "fp6_score.py"]
    frozen["code_sha256"] = {c: sha(f"{HERE}/{c}") for c in code}
    frozen["dev_chain_pkl_sha256"] = sha(DEVCHAIN)
    json.dump(frozen, open(f"{HERE}/FROZEN_FLAT.json", "w"), indent=1)
    print("FROZEN written", flush=True)
