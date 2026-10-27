#!/usr/bin/env python3
# e04: LEARNED EXIT = fitted policy iteration (Longstaff-Schwartz style optimal stopping) with a small numpy GBDT.
# Decision points: the start of every slot after our entry (tick k = 1..29; forced sell at tick 30), as the engine's time-limit
# check (first feed trade of a slot). A sell decided at tick k lands at the MEASURED time-limit sell landing (deciles; median 94 ms).
# Features: only what our feed has seen before the tick (trades of slots < s_in + k), plus entry facts (M2 score, dump, landing).
# Label at tick k = value of holding one more slot and then following the current policy, minus selling now (SOL, winsorized).
# Policy: sell at the first tick where the predicted advantage <= theta. Iterate 3x (policy evaluation -> refit).
# Model selection (theta, iterations): fit on 10-24 09:45 -> 21:00, choose on VAL 21:00 -> 01:00 (engine SOL/day, M2 + IMIT1 picks);
# final model refit on all TRAIN (09:45 -> 01:00) with the chosen settings, then TEST (01:00 -> 09:45 PKT) ONCE.
# usage: nice python3 -I e04_learn.py [tag] [universe U|picks] [depth] [min_n]
import sys, os, json, time, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT

TAG = sys.argv[1] if len(sys.argv) > 1 else "gb"
UNIV = sys.argv[2] if len(sys.argv) > 2 else "U"
DEPTH = int(sys.argv[3]) if len(sys.argv) > 3 else 3
MIN_N = int(sys.argv[4]) if len(sys.argv) > 4 else 2000
OUT = f"{E.DATA}/e04_{TAG}"
THETAS = [-0.004, -0.002, -0.001, 0.0, 0.001, 0.002, 0.004, 0.006]
NIT = 3
EXTRA = ["m2", "drop", "dump_sol", "ratio_in", "ahead_in", "L_in", "grp_in", "nhold_in", "grp_now", "age_s_in", "curve_in"]


def build_matrix(d):
    D = d.D; N = len(d.t_did); K = d.K
    did = d.t_did
    ent_f = np.stack([D["m2"][did], D["drop"][did], D["sol"][did], d.trj[:, 8], d.trj[:, 7], d.trj[:, 2], D["grp"][did].astype(float),
                      d.trj[:, 9], np.zeros(N), D["age_s"][did], D["curve"][did]], 1).astype(np.float32)
    LD = E.Leaders()
    slots = (d.s_in[:, None] + np.arange(1, K)[None, :]).ravel()
    g, _, _, _, _ = LD.arrays(slots)
    X = np.concatenate([d.ft[:, :K - 1, :].reshape(N * (K - 1), -1), np.repeat(ent_f, K - 1, axis=0)], 1)
    X[:, len(d.TF) + EXTRA.index("grp_now")] = g
    names = d.TF + EXTRA
    return X, names


def policy_ticks(pred, N, K, theta, kmin=1):
    """pred: [N, K-1] predicted advantage of holding at ticks 1..K-1 -> sell tick per trajectory"""
    sell = pred <= theta
    if kmin > 1: sell[:, :kmin - 1] = False
    sell = np.concatenate([sell, np.ones((N, 1), bool)], 1)
    return sell.argmax(1) + 1


def cont_values(pred, V_, theta):
    """V_pi(k) for k = 1..K under the policy (sell at the first tick >= k with pred <= theta; forced at K)"""
    N, K1 = pred.shape; K = K1 + 1
    out = np.zeros((N, K + 2))
    out[:, K] = V_[:, K]
    for k in range(K - 1, 0, -1):
        s = pred[:, k - 1] <= theta
        out[:, k] = np.where(s, V_[:, k], out[:, k + 1])
    return out


def engine_eval(d, ksell, period, which, lmode="meas", R=16, r=0):
    val, tdec, knd = d.tick_policy(ksell)
    pnl = d.pnl(val, r)
    e = d.engine(d.picks(which), pnl, tdec, knd, lmode=lmode, R=R, period=period)
    return V.fmt_day(e["pnl"], period), e


def per_fill(d, ksell, period, which, r=0):
    D = d.D
    val, _, _ = d.tick_policy(ksell); pnl = d.pnl(val, r)
    m = d.picks(which) & (D["near_f"] | D["near_a"]) & (D["t"] >= period[0]) & (D["t"] < period[1])
    ti = d.tidx[np.flatnonzero(m)][:, :10].ravel(); ti = ti[ti >= 0]
    return float(pnl[ti].mean()), ti


def fit_iterate(d, X, names, fit_tr, theta_for_iter, es_mask, log):
    """policy iteration on the trajectories in fit_tr (bool over trajectories). Returns list of models (one per iteration) and preds"""
    N = len(d.t_did); K = d.K; V_ = d.tv[:, 0, :]
    rows_tr = np.repeat(fit_tr, K - 1); rows_es = np.repeat(es_mask, K - 1)
    edges = GT.edges_of(X, rows_tr & ~rows_es, nb=32)
    Bm = GT.binize(X, edges)
    pred = np.full((N, K - 1), -1.0)          # iteration 0 continuation: sell at the next tick
    models = []
    for it in range(NIT):
        if it == 0:
            cont = V_[:, 2:K + 1]                       # hold at k -> sell at k+1
        else:
            cv = cont_values(pred, V_, theta_for_iter)
            cont = cv[:, 2:K + 1]
        y = (cont - V_[:, 1:K]).ravel()
        lo, hi = np.percentile(y[rows_tr], [1, 99]); y = np.clip(y, lo, hi)
        m = GT.fit(Bm, y, rows_tr & ~rows_es, rows_tr & rows_es, loss="l2", rounds=500, lr=0.05, depth=DEPTH, min_n=MIN_N, lam=10.0,
                   sub=0.5, fsub=0.7, seed=it, patience=60)
        p = GT.predict(m, Bm).reshape(N, K - 1)
        imp = GT.importance(m, X.shape[1])
        top = np.argsort(-imp)[:10]
        log(f"    iteration {it}: {m['best_round']} trees; label mean {1000 * y[rows_tr].mean():+.2f} mSOL; top features "
            + ", ".join(f"{names[j]} {imp[j]:.2f}" for j in top))
        pred = p; models.append(dict(model=m, edges=edges))
    return models, pred


if __name__ == "__main__":
    T0 = time.time()
    lines = []
    def log(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D; N = len(d.t_did); K = d.K
    X, names = build_matrix(d)
    log(f"design matrix {X.shape} ({time.time() - T0:.0f} s); universe {UNIV}, depth {DEPTH}, min_n {MIN_N}")
    tt = D["t"][d.t_did]
    if UNIV == "picks": inU = (D["pick_m2"] | D["pick_im"])[d.t_did]
    else: inU = np.ones(N, bool)
    PER = {"val": (V.VAL0, V.SPLIT), "test": (V.SPLIT, V.W1), "train": (V.W0, V.SPLIT)}
    # ---------------- stage 1: fit on 09:45 -> 21:00 (early stop on its last 2 h), choose theta on VAL
    fit1 = inU & (tt >= V.W0) & (tt < V.VAL0); es1 = tt >= V.VAL0 - 2 * 3600
    res = dict(stage1={}, final={})
    best = None
    for th_it in (0.0, 0.002):
        log(f"\nSTAGE 1 (fit 09:45 -> 21:00), iteration theta {th_it}")
        models, pred = fit_iterate(d, X, names, fit1, th_it, es1, log)
        for th in THETAS:
            ks = policy_ticks(pred, N, K, th)
            r = {}
            for w in ("M2", "IMIT1"):
                dv, e = engine_eval(d, ks, PER["val"], w)
                pf, _ = per_fill(d, ks, PER["val"], w)
                r[w] = (dv, pf)
            score = r["M2"][0] + r["IMIT1"][0]
            log(f"   theta {th:+.3f}: VAL M2 {r['M2'][0]:+.2f}/day (pf {1000 * r['M2'][1]:+.1f}) IMIT1 {r['IMIT1'][0]:+.2f}/day "
                f"(pf {1000 * r['IMIT1'][1]:+.1f}); mean sell tick on VAL picks {ks[(tt >= V.VAL0) & (tt < V.SPLIT)].mean():.1f}")
            res["stage1"][f"{th_it}_{th}"] = r
            if best is None or score > best[0]: best = (score, th_it, th)
    for w in ("M2", "IMIT1"):
        dv, _ = engine_eval(d, np.full(N, 4), PER["val"], w); pf, _ = per_fill(d, np.full(N, 4), PER["val"], w)
        log(f"   reference TODAY c4 on VAL: {w} {dv:+.2f}/day (pf {1000 * pf:+.1f})")
    log(f"  chosen on VAL: iteration theta {best[1]}, decision theta {best[2]} (score {best[0]:+.2f})")
    # ---------------- final: refit on all TRAIN with the chosen settings; TEST once
    fitF = inU & (tt >= V.W0) & (tt < V.SPLIT); esF = (tt >= V.SPLIT - 2.5 * 3600) & (tt < V.SPLIT)
    log(f"\nFINAL (fit 09:45 -> 01:00, early stop on 22:30 -> 01:00)")
    models, pred = fit_iterate(d, X, names, fitF, best[1], esF, log)
    ks = policy_ticks(pred, N, K, best[2])
    pickle.dump(dict(models=models, names=names, theta=best[2], theta_it=best[1], depth=DEPTH, min_n=MIN_N, univ=UNIV), open(f"{OUT}_model.pkl", "wb"))
    np.save(f"{OUT}_ksell.npy", ks)
    for pn in ("train", "test"):
        for w in ("M2", "IMIT1"):
            for lm in ("meas", "35", "50", "75"):
                dv, e = engine_eval(d, ks, PER[pn], w, lmode=lm)
                d4, e4 = engine_eval(d, np.full(N, 4), PER[pn], w, lmode=lm)
                log(f"  {pn:5s} {w:5s} landing {lm:4s}: learned {dv:+6.2f}/day ({e['fills']:.0f} fills)  vs TODAY c4 {d4:+6.2f}/day  diff {dv - d4:+.2f}")
            res["final"][f"{pn}_{w}"] = dv
    json.dump(res, open(f"{OUT}.json", "w"))
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    log(f"done {time.time() - T0:.0f} s")
