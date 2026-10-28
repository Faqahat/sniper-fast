#!/usr/bin/env python3
"""FOLLOW step 7 (read-only): robustness checks of the f4/f5 selector on the test days (same chosen cap / threshold per day).
 (a) LATE START: every armed window goes live 1 or 2 slots (212 / 424 ms) after the decision instead of +50 ms (feed + first attempt).
 (b) THINNING BIAS: is the live miss (model fill 0.84 vs live 0.44) related to the crossing's value? Live pre-send windows (g2_engine)
     whose crossing is in f2's valued set: model value of that crossing, live-filled vs live-missed windows (MEASURED split).
 (c) ONE-FEATURE RULE: arm when the whale's 24-h past-dump 2-slot value (wh_ide24) >= x, x and cap chosen on d-1 (engine-simple).
Out: f7.txt"""
import sys, time, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
import dv8lib as L
from f4_wf import load, account, CI_FIT
OUT = FL.OUT
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    Z = pickle.load(open(f"{OUT}/f4.pkl", "rb")); S = np.load(f"{OUT}/f4_scores.npz")
    # (a) late start
    P("# (a) window goes live later than +50 ms after the decision: calibrated NOW SOL per test day (k 4, <= 5 tokens)")
    P("| Day | +50 ms (base) | +1 slot | +2 slots |"); P("|---|---|---|---|")
    for d in sorted(Z["R"]):
        _, ci, thr, _ = Z["R"][d]["choice"]; s = S[f"s{d}"]; sel = np.flatnonzero((day == d) & (s >= thr))
        out = []
        for sh in (0.0, 162.0, 374.0):
            m2 = meta.copy(); m2["t_c"] = m2["t_c"] + sh
            out.append(account(FL.replay(sel, m2, labs, ci, CV, ccr, U, conc=5))[0])
        P(f"| D{d} | {out[0]:+.2f} | {out[1]:+.2f} | {out[2]:+.2f} |")
    # (b) thinning bias on live windows
    R = np.load(f"{OUT}/tape.npy", mmap_mode="r")
    ids, idm = L.ids_map()
    cvm = np.asarray(R["mint"])[CV["row"]].astype(np.int64); cvs = np.asarray(R["slot"])[CV["row"]].astype(np.int64)
    by = collections.defaultdict(list)
    for i, m in enumerate(cvm.tolist()): by[m].append(i)
    Gd = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g2_engine.pkl", "rb"))
    vf, vm = [], []
    for run, Xr in Gd.items():
        if not Xr.get("ps_live"): continue
        for a in Xr["arms"]:
            mint, whale, ts, ens, es, why, filled = a[:7]
            m = idm.get(mint)
            if m is None: continue
            ii = [i for i in by.get(m, []) if ts <= cvs[i] <= (es if es else ens)]
            if not ii: continue
            i = ii[0]; v = float(np.mean([CV["val"][i, q, 0, 0] if CV["fill"][i, q] else np.nan for q in range(4)]))
            if np.isnan(v): continue
            (vf if filled else vm).append(v)
    vf, vm = np.array(vf), np.array(vm)
    P(f"\n# (b) live pre-send windows with a valued crossing: live FILLED {len(vf)} windows, model value of the first crossing "
      f"{1000 * vf.mean():+.2f} mSOL (median {1000 * np.median(vf):+.2f}); live MISSED {len(vm)}: {1000 * vm.mean():+.2f} (median {1000 * np.median(vm):+.2f}) "
      f"[gross WAVE, full followers, per filled draw]")
    # (c) one-feature rule
    j = names.index("wh_ide24"); x = np.nan_to_num(F[:, j], nan=-9.0)
    P("\n# (c) one-feature rule: arm at any checkpoint when wh_ide24 >= x (x, cap chosen on d-1); calibrated NOW SOL")
    P("| Day | cap / x | fills | calibrated NOW | fol 0.9 |"); P("|---|---|---|---|---|")
    for d in sorted(Z["R"]):
        vd = day == d - 1; te = day == d; best = None
        for ci in CI_FIT:
            for thr in (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08):
                v = account(FL.replay(np.flatnonzero(vd & (x >= thr)), meta, labs, ci, CV, ccr, U, conc=5))
                if best is None or v[0] > best[0]: best = (v[0], ci, thr)
        _, ci, thr = best; sel = np.flatnonzero(te & (x >= thr))
        a = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5)); a9 = account(FL.replay(sel, meta, labs, ci, CV, ccr, U, conc=5, fol=1))
        P(f"| D{d} | {CAPS[ci]} / {thr} | {a[2]:.0f} | {a[0]:+.2f} | {a9[0]:+.2f} |")
    P(f"({time.time() - t0:.0f}s)")
    open(f"{OUT}/f7.txt", "w").write("\n".join(P_) + "\n")


if __name__ == "__main__":
    main()
