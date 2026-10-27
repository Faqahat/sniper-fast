#!/usr/bin/env python3
# e09: a SMALL readable version of the learned exit for the engine. A depth-3 / depth-4 regression tree fit on TRAIN rows only
# (ticks 1..20) to (a) the final GBDT's predictions ("distilled") and (b) the label directly. Same policy form: sell at the first
# tick where the tree's predicted advantage of holding <= theta (the GBDT's theta, chosen on VAL), forced at tick 20.
# Prints the trees with thresholds in real units; evaluates on TRAIN / TEST (M2, IMIT1; measured landing + 35/50/75) and live fills.
# usage: nice python3 -I e09_distill.py <gbdt tag, e.g. h1248>
import sys, os, json, pickle, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_gbdt as GT, gbdt_np as GB, e04_learn as L4, e_apply as AP

TAG = sys.argv[1] if len(sys.argv) > 1 else "h1248"


def tree_fit(Bm, z, rows, depth, min_n):
    mu = float(z[rows].mean())
    gr = -(z - mu); he = np.ones(len(z))
    t = GB.build(Bm, gr, he, np.flatnonzero(rows), depth, lam=1.0, min_n=min_n, fsub=np.arange(Bm.shape[1]))
    return mu, t


def tree_pred(mu, t, Bm):
    return mu + GB.pred(t, Bm)


def show(t, names, edges, mu, ind="    "):
    out = []
    def rec(n, pre):
        if "w" in n:
            out.append(f"{pre}-> hold advantage {1000 * (mu + n['w']):+.2f} mSOL"); return
        f = n["f"]; b = n["b"]; e = edges[f]
        thr = e[b - 1] if 1 <= b <= len(e) else float("nan")
        out.append(f"{pre}if {names[f]} < {thr:.4g}:")
        rec(n["l"], pre + "  ")
        out.append(f"{pre}else ({names[f]} >= {thr:.4g}):")
        rec(n["r"], pre + "  ")
    rec(t, ind)
    return out


if __name__ == "__main__":
    T0 = time.time()
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D; N = len(d.t_did); K = d.K
    M = pickle.load(open(f"{E.DATA}/e04b_{TAG}_model.pkl", "rb"))
    X, names = L4.build_matrix(d)
    mm = M["models"][0]; Bm = GT.binize(X, mm["edges"]); edges = mm["edges"]
    P = GT.predict(mm["model"], Bm)
    import e04b_learn_labels as LB
    y = LB.labels(d, M["H"]).ravel()
    tt = np.repeat(D["t"][d.t_did], K - 1); kk = np.tile(np.arange(1, K), N); li = np.repeat(d.t_li, K - 1)
    tr = (tt >= V.W0) & (tt < V.SPLIT) & (kk <= 20) & (li <= 12)
    lo, hi = np.percentile(y[tr], [1, 99]); yc = np.clip(y, lo, hi)
    th = 0.0005; cap = M["cap"]          # the ensemble's fixed threshold (+0.5 mSOL); the VAL choice of a single run is unstable (EXIT_MODEL.md)
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    res = {}
    for nm, z, depth, mn in (("distill_d3", P, 3, 20000), ("distill_d4", P, 4, 20000), ("direct_d3", yc, 3, 20000)):
        mu, t = tree_fit(Bm, z, tr, depth, mn)
        pr = tree_pred(mu, t, Bm).reshape(N, K - 1)
        sell = np.concatenate([pr <= th, np.ones((N, 1), bool)], 1); sell[:, cap - 1:] = True
        ks = sell.argmax(1) + 1
        np.save(f"{E.DATA}/e09_{TAG}_{nm}_ksell.npy", ks)
        pickle.dump(dict(mu=mu, tree=t, edges=edges, names=names, theta=th, cap=cap), open(f"{E.DATA}/e09_{TAG}_{nm}.pkl", "wb"))
        L(f"\n{nm}: tree on TRAIN rows (ticks 1..20), sell when the leaf's hold advantage <= {1000 * th:+.1f} mSOL, forced at tick {cap}")
        for s in show(t, names, edges, mu): L(s)
        agree = np.mean((pr.ravel()[tr] > th) == (P[tr] > th))
        L(f"   agreement with the GBDT's hold/sell decision on TRAIN rows: {agree:.3f}")
        for pn in ("train", "test"):
            for w in ("M2", "IMIT1"):
                s = f"   {pn:5s} {w:5s}"
                for lm in ("meas", "35", "50", "75"):
                    dv, _ = L4.engine_eval(d, ks, PER[pn], w, lmode=lm); d4, _ = L4.engine_eval(d, np.full(N, 4), PER[pn], w, lmode=lm)
                    s += f" | {lm} {dv:+6.2f} vs c4 {d4:+6.2f}"
                L(s)
    open(f"{E.DATA}/e09_{TAG}.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")
