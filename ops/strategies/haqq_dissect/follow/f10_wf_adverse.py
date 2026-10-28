#!/usr/bin/env python3
"""FOLLOW step 10 (read-only): the walk-forward REDONE with the value-dependent live fill model (f9 PF_b, MEASURED on live windows)
inside the LABELS (exact expectation: each crossing fills with PF_b x the draw's fill; a miss leaves the window armed for the next one).
Models for caps 25 and 50 (the caps chosen on most days), trained <= d-2; cap and threshold chosen on d-1 by the replay with PF_b;
test d. Same output format as f4 (f10.pkl, f10_scores.npz) so f5 can replay it and write the decision log (python3 f5_test.py f10).
Out: f10.txt, f10.pkl, f10_scores.npz"""
import sys, time, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
from f4_wf import load, account, QS
from f9_adverse import pf_bucket
OUT = FL.OUT
CI = (1, 2)
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def labels_pfj(labs, CV, ccr, t_c, ci, PFJ, fol=0, pol=0):
    n = len(labs); V = np.zeros(n); Pf = np.zeros(n); A = np.zeros(n)
    fill = CV["fill"]; val = CV["val"]; ND = fill.shape[1]
    for i in range(n):
        S, wend = labs[i][ci]; T0 = t_c[i]
        if not S: A[i] = max((wend - T0) / FL.SMS, 1.0); continue
        v = p = a = 0.0
        for d in range(ND):
            nr = 1.0
            for j in S:
                if not fill[j, d]: continue
                q = nr * PFJ[j, d]; v += q * val[j, d, fol, pol]; p += q; a += q * (ccr[j] - T0); nr *= 1 - PFJ[j, d]
            a += nr * (wend - T0)
        V[i] = v / ND; Pf[i] = p / ND; A[i] = max(a / ND / FL.SMS, 1.0)
    return V, Pf, A


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    pfb, PFJ = pf_bucket(CV)
    P(f"# FOLLOW walk-forward with value-dependent live fill PF_b {pfb.round(3).tolist()} in labels and replay ({time.time() - t0:.0f}s)")
    LAB = {ci: labels_pfj(labs, CV, ccr, meta["t_c"], ci, PFJ) for ci in CI}
    for ci in CI:
        V, Pf, A = LAB[ci]; y = 1000 * FL.net(V, Pf, A, cal=True)
        P(f"cap {CAPS[ci]}: mean label {y.mean():+.3f} mSOL, P(fill) {Pf.mean():.3f}, share > 0 {(y > 0).mean():.3f} ({time.time() - t0:.0f}s)")
    R = {}; MODELS = {}; SC = {}
    P("| Day | cap / thr (chosen on d-1) | d-1 value | fills | calibrated NOW | fol 0.9 | fol 0.8 | S2 |"); P("|---|---|---|---|---|---|---|---|")
    for d in range(2, 7):
        tr = day <= d - 2; vd = day == d - 1; te = day == d
        Bm, edges = FL.binize(F, tr)
        idx = np.flatnonzero(tr); cut = idx[int(len(idx) * 0.8)]
        trn = tr & (np.arange(len(F)) < cut); va = tr & (np.arange(len(F)) >= cut)
        best = None
        for ci in CI:
            V, Pf, A = LAB[ci]; y = np.clip(1000 * FL.net(V, Pf, A, cal=True), -30, 60)
            M = FL.fit(Bm, y, trn, va, seed=d * 10 + ci + 5)
            s = FL.predict(M, Bm); MODELS[(d, ci)] = dict(M=M, edges=edges)
            for thr in sorted(set([float(np.quantile(s[vd], 1 - q)) for q in QS] + [0.0, 1.0, 2.0])):
                v = account(FL.replay(np.flatnonzero(vd & (s >= thr)), meta, labs, ci, CV, ccr, U, conc=5, PFJ=PFJ))
                if best is None or v[0] > best[0]: best = (v[0], ci, thr, v, s)
        R[d] = dict(choice=best[:4]); SC[f"s{d}"] = best[4]
        _, ci, thr, _, s = best; sel = np.flatnonzero(te & (s >= thr))
        a = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, PFJ=PFJ)); a2 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, PFJ=PFJ), fillc=FL.FILL_S2)
        a9 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=1, PFJ=PFJ)); a8 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=2, PFJ=PFJ))
        P(f"| D{d} | {CAPS[ci]} / {thr:+.2f} | {best[0]:+.2f} | {a[2]:.0f} | {a[0]:+.2f} | {a9[0]:+.2f} | {a8[0]:+.2f} | {a2[0]:+.2f} |  ({time.time() - t0:.0f}s)")
    pickle.dump(dict(R=R, MODELS=MODELS, names=names, CAPS=CAPS, pfb=pfb), open(f"{OUT}/f10.pkl", "wb"))
    np.savez_compressed(f"{OUT}/f10_scores.npz", **SC)
    open(f"{OUT}/f10.txt", "w").write("\n".join(P_) + "\n")


if __name__ == "__main__":
    main()
