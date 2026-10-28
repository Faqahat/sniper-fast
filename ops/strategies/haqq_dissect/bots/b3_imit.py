#!/usr/bin/env python3
"""BOTS step 3 (read-only): causal imitation model per bot (247, 248): P(bot buys this dump | decision-time features), logistic GBDT
(dd_gbdt), walk-forward: the score for day D comes from a model trained on days < D only (early stop on the last 20 % of train by time;
negatives subsampled 25 %, weight 4). Two feature sets:
  TAPE = dv8's 28 tape features + leader client + near (nothing about haqq)                     <- what 'our 247' may use
  FULL = TAPE + haqq state (hq_prev, hq_open, per-code open lots, same-code previous lot)      <- describes him
Metrics per test day: AUC; precision / recall at the threshold that flags as many dumps on the TRAIN days as he bought there
(rate-matched); his net on the flagged dumps; top-k precision with k = his buys that day (hindsight, info only).
Out: bots/b3_scores.npz (OOS scores D1-D6 per bot and set), b3.txt"""
import sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
HQF = ("hq_prev", "hq_open", "open247", "open248", "open244", "open_other", "prev247_ret", "prev247_s", "prev248_ret", "prev248_s")


def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1))


def main():
    t0 = time.time()
    Z = np.load(f"{OUT}/b2.npz"); XF = Z["XF"].astype(np.float64); fn = [str(x) for x in Z["fnames"]]
    use = Z["use"]; day = Z["day"]; bt_order = np.arange(len(day))
    lines = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    sets = {"TAPE": [i for i, n in enumerate(fn) if n not in HQF], "FULL": list(range(len(fn)))}
    SC = {}
    rng = np.random.default_rng(5)
    P("# Imitation models, walk-forward (train days < D, test day D), dv8 universe usable non-mayhem dumps (MEASURED labels)")
    P("| bot | set | test day | dumps | his buys | AUC | flagged (rate-matched) | precision | recall | his net on flagged / his net on all | top-k precision |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for bot in (247, 248):
        y = Z[f"Y{bot}"]; hn = Z[f"N{bot}"]
        for sname, cols in sets.items():
            X = XF[:, cols]
            sc_all = np.full(len(y), np.nan)
            for D in (1, 2, 3, 4, 5, 6):
                tr = use & (day < D); te = use & (day == D)
                tri = np.flatnonzero(tr)            # uni rows are in mint order; sort train by time via day then index is not time -> use cc order
                cut_mask = np.zeros(len(y), bool)
                # time order inside train: day then position (approximate within-day order is irrelevant for the last-20% split by day)
                last = tr & (day == D - 1) if D > 1 else tr
                fit_rows = tr & ~last if D > 1 else tr
                if D == 1:   # only D0 to train: split by a random 20 %
                    vv = rng.random(len(y)) < 0.2; fit_rows = tr & ~vv; last = tr & vv
                keep = y | (rng.random(len(y)) < 0.25)
                w = np.where(y, 1.0, 4.0)
                E = G.edges_of(X, np.flatnonzero(tr)); Bn = G.binize(X, E)
                mdl = G.fit(Bn, y.astype(float), fit_rows & keep, last & keep, loss="log", rounds=500, lr=0.08, depth=4, min_n=100, lam=5.0,
                            sub=0.8, fsub=0.8, seed=3, patience=50, w=w)
                s = G.predict(mdl, Bn)
                sc_all[te] = s[te]
                # rate-matched threshold on train
                rate = y[tr].mean(); th = np.quantile(s[tr], 1 - rate)
                f = te & (s >= th); yt = y & te
                k = int(yt.sum()); topk = np.argsort(-s[te])[:k]; tp_k = y[np.flatnonzero(te)[topk]].sum() / max(k, 1)
                P(f"| {bot} | {sname} | D{D} | {te.sum():,} | {k:,} | {auc(s[te], y[te]):.3f} | {f.sum():,} | {(y & f).sum() / max(f.sum(), 1):.2f} | "
                  f"{(y & f).sum() / max(k, 1):.2f} | {hn[f].sum():+.2f} / {hn[te].sum():+.2f} | {tp_k:.2f} |")
                if sname == "TAPE" and D == 5:
                    imp = G.importance(mdl, len(cols)); o = np.argsort(-imp)[:12]
                    P(f"|  | importance (D5 model): " + ", ".join(f"{fn[cols[i]]} {imp[i]:.2f}" for i in o) + " | | | | | | | | |")
            SC[f"{bot}_{sname}"] = sc_all
            print(f"  {bot} {sname} done ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{OUT}/b3_scores.npz", **SC)
    open(f"{OUT}/b3.txt", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
