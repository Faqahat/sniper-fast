#!/usr/bin/env python3
"""HAQQ_MODEL step 2 (read-only, offline): fit the haqq-selection model per decision time, time split (PREREG.md).
  train: 10-24 07:30 -> 10-26 05:15 PKT (the first ~12 h of the tape only warm up the history features)
  val  : 10-26 05:15 -> 10-26 23:15 PKT (early stopping + threshold)
  test : 10-26 23:15 -> 10-27 23:05 PKT (held out)
Model: numpy GBDT (dipdetect/dd_gbdt.py, logistic loss). Threshold = highest score with VALIDATION recall >= 80%, frozen.
Out: DATA/model_n<n>.pkl (model, edges, scores, threshold), DATA/eval.json, printed tables."""
import sys, json, pickle, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
DATA = "/home/moiz/sniper-data/haqq_model"
W0 = 1793038500
TR0, TR1, VA1, TE1 = W0 - 229500, W0 - 64800, W0, W0 + 86400 - 600
NS = [int(x) for x in sys.argv[1:]] or [0, 5, 14, 24, 47]
DROP = set()            # feature ablations can be passed via env later


def auc(y, s):
    o = np.argsort(s, kind="mergesort"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    # ties: average ranks
    ss = s[o]; i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]: j += 1
        if j > i: r[o[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    p = y.sum(); n = len(y) - p
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * n))


def thr_for_recall(y, s, rec):
    sp = np.sort(s[y == 1])[::-1]
    k = int(np.ceil(rec * len(sp))) - 1
    return float(sp[max(k, 0)])


def stats(y, s, thr):
    pk = s >= thr; tp = int((pk & (y == 1)).sum())
    rec = tp / max(int(y.sum()), 1); prec = tp / max(int(pk.sum()), 1)
    return dict(recall=rec, precision=prec, picked=int(pk.sum()), n=len(y), pos=int(y.sum()), share=float(pk.mean()),
                f1=2 * rec * prec / max(rec + prec, 1e-9), lift=prec / max(y.mean(), 1e-9))


if __name__ == "__main__":
    out = {}
    for n in NS:
        t0 = time.time()
        Z = np.load(f"{DATA}/feat_n{n}.npz")
        X = Z["X"].astype(np.float64); y = Z["y"].astype(np.float64); bt = Z["bt"]; names = list(Z["names"])
        keep = [j for j, nm in enumerate(names) if nm not in DROP]; X = X[:, keep]; names = [names[j] for j in keep]
        tr = (bt >= TR0) & (bt < TR1); va = (bt >= TR1) & (bt < VA1); te = (bt >= VA1) & (bt < TE1)
        E = G.edges_of(X, tr, nb=32); B = G.binize(X, E)
        M = G.fit(B, y, tr, va, loss="logloss", rounds=1500, lr=0.05, depth=5, min_n=100, lam=5.0, sub=0.8, fsub=0.8, seed=1, patience=120)
        s = G.predict(M, B)
        thr = thr_for_recall(y[va] == 1, s[va], 0.80) if False else thr_for_recall(y[va].astype(int), s[va], 0.80)
        r = dict(n=n, best_round=M["best_round"], thr=thr,
                 auc=dict(train=auc(y[tr].astype(int), s[tr]), val=auc(y[va].astype(int), s[va]), test=auc(y[te].astype(int), s[te])),
                 val=stats(y[va].astype(int), s[va], thr), test=stats(y[te].astype(int), s[te], thr),
                 sizes=dict(train=int(tr.sum()), val=int(va.sum()), test=int(te.sum()), pos_train=int(y[tr].sum()), pos_val=int(y[va].sum()), pos_test=int(y[te].sum())))
        # PR curve on test (by test-recall level) and with thresholds frozen from val recall levels
        r["test_curve"] = []
        for rl in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98):
            tv = thr_for_recall(y[va].astype(int), s[va], rl)
            r["test_curve"].append(dict(val_recall=rl, frozen=stats(y[te].astype(int), s[te], tv),
                                        oracle=stats(y[te].astype(int), s[te], thr_for_recall(y[te].astype(int), s[te], rl))))
        al = Z["already"]
        tt = te & (y == 1)
        r["test_recall_by_already"] = dict(already=float((s[tt & al] >= thr).mean()) if (tt & al).any() else None, n_already=int((tt & al).sum()),
                                           not_yet=float((s[tt & ~al] >= thr).mean()) if (tt & ~al).any() else None, n_not_yet=int((tt & ~al).sum()))
        imp = G.importance(M, len(names)); oi = np.argsort(imp)[::-1][:20]
        r["importance"] = [(names[j], round(float(imp[j]), 4)) for j in oi]
        out[n] = r
        pickle.dump(dict(model=M, edges=E, names=names, score=s, thr=thr, mint=Z["mint"], bt=bt, y=Z["y"], slot=Z["slot"], already=al),
                    open(f"{DATA}/model_n{n}.pkl", "wb"))
        tv = r["test"]
        print(f"n={n:2d} slots: rounds {M['best_round']}, AUC tr/va/te {r['auc']['train']:.3f}/{r['auc']['val']:.3f}/{r['auc']['test']:.3f} | "
              f"VAL rec {r['val']['recall']:.3f} prec {r['val']['precision']:.3f} | TEST rec {tv['recall']:.3f} prec {tv['precision']:.3f} "
              f"picked {tv['picked']}/{tv['n']} ({100 * tv['share']:.1f}%) F1 {tv['f1']:.3f} lift {tv['lift']:.2f} | base {tv['pos'] / tv['n']:.3f} "
              f"| already-traded rec {r['test_recall_by_already']} ({time.time() - t0:.0f}s)", flush=True)
        for c in r["test_curve"]:
            f, o = c["frozen"], c["oracle"]
            print(f"   val-rec {c['val_recall']:.2f}: test rec {f['recall']:.3f} prec {f['precision']:.3f} share {100 * f['share']:.1f}% | "
                  f"at test rec {c['val_recall']:.2f}: prec {o['precision']:.3f} share {100 * o['share']:.1f}%")
        print("   top features:", r["importance"][:12], flush=True)
    json.dump({str(k): v for k, v in out.items()}, open(f"{DATA}/eval{'_' + '_'.join(map(str, NS)) if len(NS) < 5 else ''}.json", "w"), indent=1)
