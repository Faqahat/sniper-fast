#!/usr/bin/env python3
# e04b: LEARNED EXIT, multi-horizon "should I hold a bit longer" regression (the plain policy iteration of e04 was unstable: its
# 3rd iteration found no signal and collapsed to hold-everything). At the start of each slot k after our buy (k = 1..20), the GBDT
# predicts y = mean over h in H of [V(k + h) - V(k)] (SOL; V = value of a sell decided at that tick, landing at the MEASURED
# time-limit sell offsets), from the causal tick features + entry facts. Policy: sell at the first tick where the prediction <= theta
# (forced at tick `cap`).
# Selection (theta): fit on 10-24 09:45 -> 21:00 (early stop on its last 2 h), choose on VAL 21:00 -> 01:00 by engine SOL/day
# (M2 + IMIT1, measured landing). Final: refit on all TRAIN (09:45 -> 01:00), then TEST (01:00 -> 09:45) once, and our real live fills.
# usage: nice python3 -I e04b_learn.py <tag> <H e.g. 1,2,4,8> [depth] [min_n] [cap] [universe U|picks]
import sys, os, json, time, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT, e04_learn as L4

TAG = sys.argv[1]; H = [int(x) for x in sys.argv[2].split(",")]
DEPTH = int(sys.argv[3]) if len(sys.argv) > 3 else 3
MIN_N = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
CAP = int(sys.argv[5]) if len(sys.argv) > 5 else 20
UNIV = sys.argv[6] if len(sys.argv) > 6 else "U"
SEED = int(sys.argv[7]) if len(sys.argv) > 7 else 1
KTR = 20
OUT = f"{E.DATA}/e04b_{TAG}"
THETAS = [-0.006, -0.004, -0.003, -0.002, -0.001, -0.0005, 0.0, 0.0005, 0.001, 0.002, 0.003]


def labels(d):
    K = d.K; Vv = d.tv[:, 0, :]
    N = len(d.t_did); y = np.zeros((N, K - 1))
    for k in range(1, K):
        acc = 0.0
        for h in H: acc = acc + Vv[:, min(K, k + h)] - Vv[:, k]
        y[:, k - 1] = acc / len(H)
    return y


def policy(pred, N, K, theta, cap):
    sell = pred <= theta
    sell = np.concatenate([sell, np.ones((N, 1), bool)], 1)
    sell[:, cap - 1:] = True
    return sell.argmax(1) + 1


def fit(d, X, y, fit_tr, es, log):
    N = len(d.t_did); K = d.K
    kk = np.tile(np.arange(1, K), N)
    rows = np.repeat(fit_tr, K - 1) & (kk <= KTR)
    rows_es = rows & np.repeat(es, K - 1)
    rows_fit = rows & ~rows_es
    edges = GT.edges_of(X, rows_fit, nb=32)
    Bm = GT.binize(X, edges)
    yy = y.ravel().copy(); lo, hi = np.percentile(yy[rows_fit], [1, 99]); yy = np.clip(yy, lo, hi)
    m = GT.fit(Bm, yy, rows_fit, rows_es, loss="l2", rounds=600, lr=0.04, depth=DEPTH, min_n=MIN_N, lam=10.0, sub=0.5, fsub=0.7, seed=SEED, patience=80)
    p = GT.predict(m, Bm)
    # out-of-sample fit quality on the early-stopping rows
    ve = rows_es
    r2 = 1 - np.mean((yy[ve] - p[ve]) ** 2) / np.var(yy[ve])
    imp = GT.importance(m, X.shape[1]); top = np.argsort(-imp)[:12]
    log(f"    {m['best_round']} trees, held-out R2 {r2:+.4f}; label mean {1000 * yy[rows_fit].mean():+.2f} mSOL; top: "
        + ", ".join(f"{NAMES[j]} {imp[j]:.2f}" for j in top))
    return dict(model=m, edges=edges, r2=r2), p.reshape(N, K - 1)


if __name__ == "__main__":
    T0 = time.time()
    lines = []
    def log(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D; N = len(d.t_did); K = d.K
    X, NAMES = L4.build_matrix(d)
    y = labels(d)
    tt = D["t"][d.t_did]
    inU = np.ones(N, bool) if UNIV == "U" else (D["pick_m2"] | D["pick_im"])[d.t_did]
    inU &= d.t_li <= 12
    log(f"e04b {TAG}: horizons {H}, depth {DEPTH}, min_n {MIN_N}, cap {CAP}, universe {UNIV}; matrix {X.shape}")
    PER = {"val": (V.VAL0, V.SPLIT), "test": (V.SPLIT, V.W1), "train": (V.W0, V.SPLIT)}
    log("STAGE 1: fit 09:45 -> 21:00, choose theta on VAL 21:00 -> 01:00")
    m1, p1 = fit(d, X, y, inU & (tt >= V.W0) & (tt < V.VAL0), tt >= V.VAL0 - 2 * 3600, log)
    best = None; ref = {}
    for w in ("M2", "IMIT1"):
        ref[w] = L4.engine_eval(d, np.full(N, 4), PER["val"], w)[0]
    log(f"   TODAY c4 on VAL: M2 {ref['M2']:+.2f}/day, IMIT1 {ref['IMIT1']:+.2f}/day")
    for th in THETAS:
        ks = policy(p1, N, K, th, CAP)
        r = {w: L4.engine_eval(d, ks, PER["val"], w)[0] for w in ("M2", "IMIT1")}
        mv = (tt >= V.VAL0) & (tt < V.SPLIT)
        log(f"   theta {th * 1000:+.1f} mSOL: VAL M2 {r['M2']:+6.2f} IMIT1 {r['IMIT1']:+6.2f}  (mean sell tick {ks[mv].mean():.1f})")
        sc = r["M2"] + r["IMIT1"]
        if best is None or sc > best[0]: best = (sc, th)
    log(f"   chosen theta {best[1] * 1000:+.1f} mSOL")
    log("FINAL: refit on all TRAIN 09:45 -> 01:00 (early stop on 22:30 -> 01:00)")
    mF, pF = fit(d, X, y, inU & (tt >= V.W0) & (tt < V.SPLIT), (tt >= V.SPLIT - 2.5 * 3600), log)
    ks = policy(pF, N, K, best[1], CAP)
    np.save(f"{OUT}_ksell.npy", ks)
    pickle.dump(dict(models=[mF], names=NAMES, theta=best[1], H=H, cap=CAP, depth=DEPTH, min_n=MIN_N), open(f"{OUT}_model.pkl", "wb"))
    for pn in ("train", "test"):
        for w in ("M2", "IMIT1"):
            s = f"  {pn:5s} {w:5s}"
            for lm in ("meas", "measc", "35", "50", "75"):
                dv, e = L4.engine_eval(d, ks, PER[pn], w, lmode=lm); d4, _ = L4.engine_eval(d, np.full(N, 4), PER[pn], w, lmode=lm)
                s += f" | {lm} {dv:+6.2f} vs c4 {d4:+6.2f}"
            log(s)
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    log(f"done {time.time() - T0:.0f} s")
