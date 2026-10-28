#!/usr/bin/env python3
"""BOTS step 11 (read-only): BROAD imitation model on the trigger envelope of b2b (every outside sell on non-mayhem tokens <= 300 s old)
restricted to the classes that precede 99 % / 95 % of 247 / 248 buys: A single sell >= 5 %, B dev sell, C cs/early holder >= 1 %, D holder
>= 2 % (usable hours). Label = bot bought within 0..2 slots (MEASURED). Logistic GBDT, walk-forward: day D scored by a model trained on
days < D (early stop on D-1; negatives subsampled 10 %, weight 10). Features (decision time): drop, dd10, sell SOL, seller type, seller's
balance before (% supply) and share sold, chunk counts 10 / 30 slots, dev sells so far, curve SOL after, age, outside buy / sell SOL last 3
slots, trades so far.
Out: bots/b11.npz (envelope mask + OOS scores), b11.txt"""
import sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"


def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1))


def main():
    t0 = time.time()
    Z = np.load(f"{OUT}/b2b.npz")
    st = Z["stype"]; d = Z["drop"]; h = Z["hold"]
    env = Z["usable"] & ((d >= 0.05) | (st == 0) | (np.isin(st, (1, 2)) & (h >= 1)) | (h >= 2))
    cols = ["drop", "dd10", "sol", "hold", "frac", "ch10", "ch30", "cdev", "vpost", "age", "b3", "s3", "ntr"]
    Xf = np.column_stack([Z[c].astype(np.float64) for c in cols] + [(st == k).astype(np.float64) for k in range(4)])
    fn = cols + ["st_dev", "st_cs", "st_early", "st_other"]
    day = Z["day"].astype(int)
    lines = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    P(f"# Broad imitation (envelope A-D, usable): {env.sum():,} sells; walk-forward")
    P("| bot | test day | sells | his buys | AUC | flagged (rate-matched) | precision | recall |"); P("|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(2)
    SC = {}
    for bot in (247, 248):
        y = Z[f"Y{bot}"].astype(bool); s_all = np.full(len(y), np.nan)
        for D in (1, 2, 3, 4, 5, 6):
            tr = env & (day < D); te = env & (day == D)
            if D > 1: va = tr & (day == D - 1); fi = tr & ~va
            else:
                vv = rng.random(len(y)) < 0.2; va = tr & vv; fi = tr & ~vv
            keep = y | (rng.random(len(y)) < 0.10)
            w = np.where(y, 1.0, 10.0)
            sub = np.flatnonzero((tr | te) & (keep | te))
            Xs = Xf[sub]; ys = y[sub]
            E = G.edges_of(Xs, np.flatnonzero(tr[sub])); B = G.binize(Xs, E)
            mdl = G.fit(B, ys.astype(float), (fi & keep)[sub], (va & keep)[sub], loss="log", rounds=400, lr=0.08, depth=4, min_n=100, lam=5.0,
                        sub=0.8, fsub=0.8, seed=3, patience=40, w=w[sub])
            s = G.predict(mdl, B)
            ss = np.full(len(y), np.nan); ss[sub] = s
            s_all[te] = ss[te]
            trk = tr & keep
            rate = y[tr].mean()
            # threshold on train rows (re-weighted quantile ~ use subsampled train rows with weights)
            st_ = ss[trk]; wt = np.where(y[trk], 1.0, 10.0); o = np.argsort(-st_); cw = np.cumsum(wt[o]) / wt.sum()
            th = st_[o][min(np.searchsorted(cw, rate), len(o) - 1)]
            f = te & (ss >= th); k = int((y & te).sum())
            P(f"| {bot} | D{D} | {te.sum():,} | {k:,} | {auc(ss[te], y[te]):.3f} | {f.sum():,} | {(y & f).sum() / max(f.sum(), 1):.2f} | {(y & f).sum() / max(k, 1):.2f} |")
            if D == 5:
                imp = G.importance(mdl, len(fn)); o = np.argsort(-imp)[:10]
                P(f"|  | importance D5: " + ", ".join(f"{fn[i]} {imp[i]:.2f}" for i in o) + " | | | | | | |")
        SC[f"S{bot}"] = s_all.astype(np.float32)
        print(f"{bot} done ({time.time() - t0:.0f}s)", flush=True)
    np.savez_compressed(f"{OUT}/b11.npz", env=env, **SC)
    open(f"{OUT}/b11.txt", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
