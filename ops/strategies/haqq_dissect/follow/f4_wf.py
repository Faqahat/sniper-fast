#!/usr/bin/env python3
"""FOLLOW step 4 (read-only): walk-forward selector + armed-window replay.
Target per checkpoint (f3 labels, INFERRED replay): CALIBRATED net of arming now with cap C, NOW costs, k = 4, wave exit, full followers
(mSOL, clipped to [-30, +60] for training only). GBDT (numpy, squared loss, depth 3) per cap C in {25, 50, 100} slots.
Walk-forward: test day d (D2..D6): models trained on days <= d-2 (early stop on the last 20 % of those rows by time); the cap and the
score threshold chosen on day d-1 by the replay's calibrated NOW net (k 4, <= 5 tokens armed at once); then applied to day d.
Replay (flib.replay): per episode the first checkpoint with score >= threshold arms until the whale's dump + 30 ms or the cap; token-level
union; fills thinned to the MEASURED live fill rate (PF 0.52); a fill blocks the token 1.4 s; arming = armed slots x k x 5,120 lamports.
Out: f4.txt, f4.pkl (models, choices, per-day results)"""
import sys, time, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
import dv8lib as L
OUT = FL.OUT
CI_FIT = (1, 2, 3)        # CAPS index: 25, 50, 100
QS = (0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2)
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def load():
    Z = np.load(f"{OUT}/feats.npz"); F = Z["F"]; meta = Z["meta"]; names = list(Z["names"]); CAPS = list(Z["CAPS"])
    labs = pickle.load(open(f"{OUT}/labs.pkl", "rb"))
    CV = dict(np.load(f"{OUT}/cross_val.npz")); X = np.load(f"{OUT}/rowx.npz"); ccr = X["cc"][CV["row"]]
    U = np.random.default_rng(12345).random(CV["fill"].shape)
    day = ((meta["bt"] - L.DAY0) // 86400).astype(int)
    return F, meta, names, CAPS, labs, CV, ccr, U, day


def account(res, k=4, fillc=FL.FILL_NOW, cal=True, keep=None, fol_val=None):
    """mean over draws: (net SOL, gross SOL, fills, armed slots); keep(j, m) -> bool restricts the counted fills (overlap test)"""
    fills, armed = res[0], res[1]
    ND = len(fills); tot = []; gro = []; nf = []
    asl = float(np.mean(sum(armed.values()))) if armed else 0.0
    for d in range(ND):
        g = 0.0; n = 0
        for j, v, m, i in fills[d]:
            if keep is not None and not keep(j, m): continue
            v = fol_val(j, d) if fol_val else v
            g += (FL.CAL_A * v + FL.CAL_B) if cal else v; n += 1
        tot.append(g - n * fillc); gro.append(g); nf.append(n)
    return float(np.mean(tot)) - asl * k * FL.TRY, float(np.mean(gro)), float(np.mean(nf)), asl


def boot_mint(res, k=4, fillc=FL.FILL_NOW, cal=True, keep=None, B=1000):
    fills, armed = res[0], res[1]
    ms = sorted(armed); ND = len(fills); per = collections.defaultdict(float)
    for d in range(ND):
        for j, v, m, i in fills[d]:
            if keep is not None and not keep(j, m): continue
            per[m] += ((FL.CAL_A * v + FL.CAL_B) if cal else v) / ND - fillc / ND
    x = np.array([per[m] - armed[m].mean() * k * FL.TRY for m in ms])
    if not len(x): return (0.0, 0.0)
    g = np.random.default_rng(1); s = [x[g.integers(0, len(x), len(x))].sum() for _ in range(B)]
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    P(f"# FOLLOW walk-forward: {len(F):,} checkpoint rows, days {np.bincount(day).tolist()} ({time.time() - t0:.0f}s)")
    t_c = meta["t_c"]
    LAB = {}
    for ci in CI_FIT:
        V, Pf, A = FL.labels(labs, CV, ccr, t_c, ci)
        LAB[ci] = (V, Pf, A)
        y = 1000 * FL.net(V, Pf, A, cal=True)
        P(f"cap {CAPS[ci]}: label mean calibrated NOW net {y.mean():+.3f} mSOL/checkpoint, P(fill) {Pf.mean():.3f}, armed slots {A.mean():.1f}; "
          f"N=0 rows: net {y[meta['N'] == 0].mean():+.3f} ({time.time() - t0:.0f}s)")
    # sanity: haqq-followed vs not (episode first checkpoint N = 0, cap 100)
    V, Pf, A = LAB[3]; y = 1000 * FL.net(V, Pf, A, cal=True); n0 = meta["N"] == 0
    P(f"sanity (N=0, cap 100, calibrated NOW mSOL per armed episode): haqq followed the whale's dump {y[n0 & meta['hqf']].mean():+.2f} "
      f"(n={int((n0 & meta['hqf']).sum()):,}), not {y[n0 & ~meta['hqf']].mean():+.2f} (n={int((n0 & ~meta['hqf']).sum()):,}); base rate {meta['hqf'][n0].mean():.3f}")
    R = {}; MODELS = {}
    for d in range(2, 7):
        tr = day <= d - 2; vd = day == d - 1; te = day == d
        if not te.any(): continue
        Bm, edges = FL.binize(F, tr)
        idx = np.flatnonzero(tr); cut = idx[int(len(idx) * 0.8)]
        trn = tr & (np.arange(len(F)) < cut); va = tr & (np.arange(len(F)) >= cut)
        best = None; cand = []
        for ci in CI_FIT:
            V, Pf, A = LAB[ci]
            y = np.clip(1000 * FL.net(V, Pf, A, cal=True), -30, 60)
            M = FL.fit(Bm, y, trn, va, seed=d * 10 + ci)
            s = FL.predict(M, Bm)
            MODELS[(d, ci)] = dict(M=M, edges=edges)
            sv = s[vd]
            thrs = sorted(set([float(np.quantile(sv, 1 - q)) for q in QS] + [0.0]))
            for thr in thrs:
                res = FL.replay(np.flatnonzero(vd & (s >= thr)), meta, labs, ci, CV, ccr, U, conc=5)
                v = account(res)
                cand.append((v[0], ci, thr, v))
                if best is None or v[0] > best[0]: best = (v[0], ci, thr, v, s)
            P(f"  test D{d}: cap {CAPS[ci]} model trees {len(M['trees'])} ({time.time() - t0:.0f}s)")
        R[d] = dict(choice=best[:4], cand=cand, s=best[4])
        P(f"D{d}: chosen on D{d - 1}: cap {CAPS[best[1]]}, thr {best[2]:+.3f} (D{d - 1} calibrated NOW {best[0]:+.2f} SOL, fills {best[3][2]:.0f}, armed slots {best[3][3]:,.0f})")
    pickle.dump(dict(R={d: dict(choice=v["choice"], cand=v["cand"]) for d, v in R.items()}, MODELS=MODELS, names=names, CAPS=CAPS), open(f"{OUT}/f4.pkl", "wb"))
    np.savez_compressed(f"{OUT}/f4_scores.npz", **{f"s{d}": v["s"] for d, v in R.items()})
    open(f"{OUT}/f4.txt", "w").write("\n".join(P_) + "\n")
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
