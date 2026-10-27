#!/usr/bin/env python3
# e15: second out-of-sample fold with the time direction reversed (a check that the result is not one lucky night).
# Fold B: fit the same learned exit (e04b settings: horizons 1,2,4,8, depth 3, min_n 1000, theta +0.5 mSOL fixed, cap 20, 3 seeds averaged)
# on 10-24 18:30 -> 10-25 09:45 (15.25 h), test on 10-24 09:45 -> 18:30 (8.75 h, never seen by the model).
# Reports the full exit and its two halves (cut only / hold only) vs c4: engine SOL/day (measured landing), 90% CI (30-min blocks).
import sys, os, json, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT, e04_learn as L4, e05_report as R5
import e04b_learn_labels as LB

H = [1, 2, 4, 8]; THETA = 0.0005; CAP = 20; KTR = 20
FIT = (E.pk("10-24 18:30"), V.W1); TEST = (V.W0, E.pk("10-24 18:30"))


def fit(X, y, rows_fit, rows_es, seed):
    edges = GT.edges_of(X, rows_fit, nb=32); Bm = GT.binize(X, edges)
    yy = y.copy(); lo, hi = np.percentile(yy[rows_fit], [1, 99]); yy = np.clip(yy, lo, hi)
    m = GT.fit(Bm, yy, rows_fit, rows_es, loss="l2", rounds=600, lr=0.04, depth=3, min_n=1000, lam=10.0, sub=0.5, fsub=0.7, seed=seed, patience=80)
    return GT.predict(m, Bm), m["best_round"]


if __name__ == "__main__":
    T0 = time.time()
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D; N = len(d.t_did); K = d.K
    X, _ = L4.build_matrix(d); y = LB.labels(d, H).ravel()
    tt = np.repeat(D["t"][d.t_did], K - 1); kk = np.tile(np.arange(1, K), N); li = np.repeat(d.t_li, K - 1)
    rows = (tt >= FIT[0]) & (tt < FIT[1]) & (kk <= KTR) & (li <= 12)
    es = rows & (tt >= FIT[1] - 2.5 * 3600)
    preds = []
    for seed in (1, 2, 3):
        p, nt = fit(X, y, rows & ~es, es, seed); preds.append(p.reshape(N, K - 1)); L(f"  seed {seed}: {nt} trees")
    pr = sum(preds) / 3
    sell = np.concatenate([pr <= THETA, np.ones((N, 1), bool)], 1); sell[:, CAP - 1:] = True
    ks = sell.argmax(1) + 1
    np.save(f"{E.DATA}/e15_reverse_ksell.npy", ks)
    P = {"TODAY_c4": np.full(N, 4), "LEARN (fold B)": ks, "cut only": np.minimum(ks, 4), "hold only": np.maximum(ks, 4)}
    L(f"FOLD B: fit {E.pkt(FIT[0])} -> {E.pkt(FIT[1])}, TEST {E.pkt(TEST[0])} -> {E.pkt(TEST[1])} PKT (8.75 h, earlier than the fit window)")
    for w in ("M2", "IMIT1"):
        rows_ = {}
        for nm, k in P.items():
            val, tdec, knd = d.tick_policy(k)
            e = d.engine(d.picks(w), d.pnl(val, 0), tdec, knd, lmode="meas", R=24, period=TEST, return_rows=True)
            rows_[nm] = e["rows"]; s = f"  {w:5s} {nm:16s} TEST {V.fmt_day(e['pnl'], TEST):+6.2f} SOL/day"
            if nm != "TODAY_c4":
                bt = R5.block_sums(d, rows_["TODAY_c4"], TEST, 24); bx = R5.block_sums(d, rows_[nm], TEST, 24)
                df = bx - bt; lo, hi = R5.boot_ci(df); sc = 24 / V.hours(TEST)
                s += f"  diff {df.sum() * sc:+.2f} [{lo * sc:+.2f}, {hi * sc:+.2f}]"
            L(s)
    # live fills in the fold-B test window (FRA r10-r11 + AMS r9-r11 hours, before 18:30? -> only fires before 18:30)
    open(f"{E.DATA}/e15_reverse.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")
