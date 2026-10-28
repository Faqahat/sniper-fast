#!/usr/bin/env python3
"""FOLLOW step 9 (read-only): ADVERSE fill selection. f7(b) MEASURED that live pre-send windows MISS the crossings the model values
most (missed +31 mSOL vs filled -1 mSOL model value). So a uniform thinning (PF 0.52) is optimistic. Here the thinning depends on the
crossing's model value: per value bucket, PF_b = live fill rate / model fill rate on the live pre-send windows (g2_engine, AMS r9-r33,
FRA r1-r26; first valued crossing per window). The f4 selector (same chosen cap / threshold per test day) is replayed with PF_b.
Also a full re-selection: thresholds re-chosen on d-1 under PF_b (models unchanged). Out: f9.txt"""
import sys, time, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
import dv8lib as L
from f4_wf import load, account, boot_mint, CI_FIT, QS
OUT = FL.OUT
EDG = (-1e9, -0.010, 0.0, 0.010, 0.030, 0.060, 1e9)
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def live_rows(CV):
    """(crossing, draw, model fill, model value, live filled) for the first valued crossing of every live pre-send window"""
    R = np.load(f"{OUT}/tape.npy", mmap_mode="r")
    ids, idm = L.ids_map()
    cvm = np.asarray(R["mint"])[CV["row"]].astype(np.int64); cvs = np.asarray(R["slot"])[CV["row"]].astype(np.int64)
    by = collections.defaultdict(list)
    for i, m in enumerate(cvm.tolist()): by[m].append(i)
    Gd = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g2_engine.pkl", "rb"))
    rows = []
    for run, Xr in Gd.items():
        if not Xr.get("ps_live"): continue
        for a in Xr["arms"]:
            mint, whale, ts, ens, es, why, filled = a[:7]
            m = idm.get(mint)
            if m is None: continue
            ii = [i for i in by.get(m, []) if ts <= cvs[i] <= (es if es else ens)]
            if not ii: continue
            i = ii[0]
            for q in range(4):
                v = float(CV["val"][i, q, 0, 0]) if CV["fill"][i, q] else np.nan
                rows.append((i, q, bool(CV["fill"][i, q]), v, bool(filled)))
    # per bucket of the draw's value: live fill / model fill (model fill = 1 for a filled draw: the bucket is defined on filled draws;
    # the model's no-fill draws are already no-fill)
    return rows


def pf_bucket(CV):
    rows = live_rows(CV)
    vals = np.array([r[3] for r in rows]); lf = np.array([r[4] for r in rows]); mf = np.array([r[2] for r in rows])
    pfb = np.array([float(lf[mf & (vals >= a) & (vals < b)].mean()) if (mf & (vals >= a) & (vals < b)).sum() else FL.PF for a, b in zip(EDG[:-1], EDG[1:])])
    bi = np.clip(np.searchsorted(np.array(EDG), CV['val'][:, :, 0, 0], side='right') - 1, 0, len(pfb) - 1)
    return pfb, pfb[bi]


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    Z = pickle.load(open(f"{OUT}/f4.pkl", "rb")); S = np.load(f"{OUT}/f4_scores.npz")
    rows = live_rows(CV)
    P("# live pre-send windows: per model-value bucket of the window's first crossing (filled draws), LIVE fill share (MEASURED)")
    P("| value bucket (mSOL, gross WAVE) | draws | windows live-filled share | PF_b (live fill / model fill) |"); P("|---|---|---|---|")
    pfb = []
    vals = np.array([r[3] for r in rows]); lf = np.array([r[4] for r in rows]); mf = np.array([r[2] for r in rows])
    for a, b in zip(EDG[:-1], EDG[1:]):
        m = mf & (vals >= a) & (vals < b)
        pf = float(lf[m].mean()) if m.sum() else FL.PF
        pfb.append(pf)
        P(f"| {1000 * a:+.0f}..{1000 * b:+.0f} | {int(m.sum())} | {pf:.3f} | {pf:.3f} |")
    pfb = np.array(pfb)
    bi = np.clip(np.searchsorted(np.array(EDG), CV["val"][:, :, 0, 0], side="right") - 1, 0, len(pfb) - 1)
    PFJ = pfb[bi]
    P(f"(overall: model-filled draws {int(mf.sum())}, live-filled share among them {lf[mf].mean():.3f})")
    P("\n# the f4/f5 selector replayed with value-dependent thinning PF_b (calibrated NOW SOL per test day; k 4, <= 5 tokens)")
    P("| Day | same cap/thr: fills | calibrated NOW [90%] | NEW-only proxy (x share new from f5) | fol 0.9 | S2 | re-chosen thr on d-1: cap / thr | test calibrated NOW | fol 0.9 |")
    P("|---|---|---|---|---|---|---|---|---|")
    f5 = pickle.load(open(f"{OUT}/f5.pkl", "rb"))["rows"]; shr = {r["d"]: (r["new"][0] / r["cal"][0] if r["cal"][0] else 0) for r in f5}
    tot = collections.defaultdict(float)
    for d in sorted(Z["R"]):
        _, ci, thr, _ = Z["R"][d]["choice"]; s = S[f"s{d}"]; sel = np.flatnonzero((day == d) & (s >= thr))
        res = FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, PFJ=PFJ)
        a = account(res); bs = boot_mint(res); a9 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=1, PFJ=PFJ)); a2 = account(res, fillc=FL.FILL_S2)
        # re-choose cap / threshold on d-1 under PF_b, using the score of each cap's model (recomputed)
        best = None
        for ci2 in CI_FIT:
            M = Z["MODELS"][(d, ci2)]; Bm = FL.apply_bins(F, M["edges"]); s2 = FL.predict(M["M"], Bm)
            vd = day == d - 1
            for t2 in sorted(set([float(np.quantile(s2[vd], 1 - q)) for q in QS] + [0.0, 2.0, 4.0])):
                v = account(FL.replay(np.flatnonzero(vd & (s2 >= t2)), meta, labs, ci2, CV, ccr, U, conc=5, PFJ=PFJ))
                if best is None or v[0] > best[0]: best = (v[0], ci2, t2, s2)
        if best[0] > 0:
            sel2 = np.flatnonzero((day == d) & (best[3] >= best[2]))
            b_ = account(FL.replay(sel2, meta, labs, best[1], CV, ccr, U, conc=5, PFJ=PFJ)); b9 = account(FL.replay(sel2, meta, labs, best[1], CV, ccr, U, conc=5, fol=1, PFJ=PFJ))
            rc = f"{CAPS[best[1]]} / {best[2]:+.2f} (d-1 {best[0]:+.2f}) | {b_[0]:+.2f} | {b9[0]:+.2f}"
        else:
            b_ = (0.0,); b9 = (0.0,); rc = f"no trade (d-1 best {best[0]:+.2f}) | 0 | 0"
        P(f"| D{d} | {a[2]:.0f} | {a[0]:+.2f} [{bs[0]:+.2f}..{bs[1]:+.2f}] | {a[0] * shr.get(d, 0):+.2f} | {a9[0]:+.2f} | {a2[0]:+.2f} | {rc} |")
        if d <= 5:
            tot["cal"] += a[0]; tot["f9"] += a9[0]; tot["rc"] += b_[0]; tot["rc9"] += b9[0]
    P(f"\nmean D2..D5 per day: same selector {tot['cal'] / 4:+.2f} (fol 0.9 {tot['f9'] / 4:+.2f}); re-chosen threshold {tot['rc'] / 4:+.2f} (fol 0.9 {tot['rc9'] / 4:+.2f}) ({time.time() - t0:.0f}s)")
    open(f"{OUT}/f9.txt", "w").write("\n".join(P_) + "\n")


if __name__ == "__main__":
    main()
