"""ENGINE_SPEC impact: dev leave-one-block-out CV of the frozen config (gbm_s, T2 q.15 / re-arm q.20) with input groups dropped or replaced.
DEV only (r37-r54); r55 not used."""
import sys, json, pickle, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np, x8_variants as V, ftab
OUTD = "/home/moiz/sniper-data/flatperfect"
FR = json.load(open("FROZEN_FLAT.json")); F0 = FR["features"]
P, cols, X0 = ftab.table(f"{OUTD}/dev_chain_full.pkl")
V.P, V.cols = P, cols; V.ci = {c: i for i, c in enumerate(cols)}
WH = ["wh_n", "wh_mints", "wh_big", "wh_q10", "wh_q50", "wh_sold_frac"]
def withwh(W):
    X = X0.copy(); d = pickle.load(open(f"{OUTD}/dev_wh_{W}.pkl", "rb"))
    for i, p in enumerate(P):
        v = d.get(p["key"])
        if v and X0[i, V.ci["cov"]] == 1:
            for c in WH: X[i, V.ci[c]] = v[c]
    return X
def run(name, feats, X):
    V.X = X
    out = V.cv(feats, ("T2", "rearm"), model="gbm_s", qs=(0.15, 0.2))
    t2 = out["T2"][0.15]; re = out["rearm"][0.2]
    f = lambda r: f"n{sum(x[0] for x in r)} fl{sum(x[1] for x in r)} w{sum(x[2] for x in r)} sv{sum(x[4] for x in r):+.2f} w/o5 {sum(x[5] for x in r):+.2f} pos{sum(x[4]>0 for x in r)}/4"
    print(f"{name:42s} | T2 q.15 {f(t2)} | rearm q.20 {f(re)} | total sv {sum(x[4] for x in t2)+sum(x[4] for x in re):+.2f}", flush=True)
drop = lambda pre: [c for c in F0 if not (c.startswith(pre) if isinstance(pre, str) else c in pre)]
run("BASELINE (frozen inputs)", F0, X0)
run("whale history: 24 h look-back", F0, withwh(403000))
run("whale history: 6 h look-back", F0, withwh(100000))
run("drop whale history wh_*", [c for c in F0 if c not in WH], X0)
run("drop shadow paper s_*", drop("s_"), X0)
run("drop own results o_*", drop("o_"), X0)
FAIL = [c for c in F0 if "fail" in c or "botsonline" in c]
run("drop failed-tx inputs (" + str(len(FAIL)) + ")", [c for c in F0 if c not in FAIL], X0)
run("drop 30-min regime g_*_30m", [c for c in F0 if not c.endswith("_30m")], X0)
run("drop all regime g_*", drop("g_"), X0)
run("drop QUIET arm fields q_*", drop("q_"), X0)
run("drop pre-fill pf_* (arm-time only)", [c for c in F0 if not c.startswith("pf_") and c not in ("g_bfail_20s", "g_botbuys_20s")], X0)
