#!/usr/bin/env python3
# Choose configs on R2 ONLY (train). For each trigger family and each queue-position assumption (with its consistent attempt
# rate k, cheap fees), grid over filters x W x y (stage 1: size 0.55, exits c4 / c6_sl10 / c2), then stage 2 (all exits x 2 sizes)
# for the 8 best stage-1 configs. Objective: R2 net SOL (all costs), >= 30 fills.  -> presend/ps6_select.json + .txt
import sys, json, itertools, time
import numpy as np
from multiprocessing import get_context
import ps5_lib as E
G = {}
INF = 1e18
def filt_sets(D):
    f = lambda k: E.wfeat(D, k); fam = D["w_fam"]; out = []
    crel = (f("cre_nprev") >= 3) & (f("cre_early") >= 0.8)
    for fm, nm in ((0, "T1"), (1, "T1t")):
        for dmin, amax, smin, first, cl in itertools.product((2.0, 4.65), (343.0, INF), (0.0, 1.08), (False, True), (False, True)):
            m = (fam == fm) & (f("drop") >= dmin) & (f("age_s") <= amax) & (f("sell_sol") >= smin)
            if first: m &= f("ndump2") == 0
            if cl: m &= crel
            out.append((nm, dict(drop_min=dmin, age_max=amax, sell_min=smin, first=first, crelist=cl), m, (5, 10, 25, 50), (False,)))
    for ht, hmin, cl in itertools.product((1, 2, 3, 0), (0.0, 3.0, 5.0, 10.0), (False, True)):
        m = (fam == 2) & (f("hpct") >= hmin)
        if ht: m &= f("htype") == ht
        if cl: m &= crel
        out.append(("T2", dict(htype=ht, hpct_min=hmin, crelist=cl), m, (5, 10, 25, 50, 100, 250), (False,)))
    for npv, emin, dmin in itertools.product((0, 1, 3, 5), (0.0, 0.6, 0.8, 0.9), (0.0, 3.0, 6.0)):
        if npv == 0 and emin > 0: continue
        m = (fam == 3) & (f("cre_nprev") >= npv) & (f("dev_pct") >= dmin)
        if npv > 0: m &= f("cre_early") >= emin
        out.append(("T3", dict(nprev_min=npv, early_min=emin, dev_pct_min=dmin), m, (5, 10, 25, 50, 100, 250), (False, True)))
    return out

def work1(i):
    D = G["D"]; nm, fp, m, Ws, ecs = G["F"][i]; res = []
    if m.sum() == 0: return res
    for W, ec, y, dm, ex in itertools.product(Ws, ecs, E.YS, E.DMOD, ("c4_tpnone_slnone", "c6_tpnone_sl10", "c2_tpnone_slnone")):
        o = E.run(D, m, W, y, dm, 0.55, ex, end_cre=ec)
        res.append((nm, i, W, ec, y, dm, 0.55, ex, o["pnl"], o["fill"], o["per_fill"], o["att_per_fill"]))
    return res

def work2(args):
    D = G["D"]; nm, i, W, ec, y, dm = args; m = G["F"][i][2]; res = []
    for size, ex in itertools.product(E.SIZES, E.EXN):
        o = E.run(D, m, W, y, dm, size, ex, end_cre=ec)
        res.append((nm, i, W, ec, y, dm, size, ex, o["pnl"], o["fill"], o["per_fill"], o["att_per_fill"]))
    return res

if __name__ == "__main__":
    t0 = time.time(); procs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    D = E.load("R2"); G["D"] = D; G["F"] = filt_sets(D); h = D["hours"]
    print(f"R2 loaded ({h:.1f} h), filter sets {len(G['F'])}, {time.time() - t0:.0f} s", flush=True)
    R1 = []
    with get_context("fork").Pool(procs) as p:
        for k, r in enumerate(p.imap_unordered(work1, range(len(G["F"])), chunksize=2)):
            R1 += r
            if (k + 1) % 20 == 0: print(f"  stage1 {k + 1}/{len(G['F'])} filters, {len(R1)} runs, {time.time() - t0:.0f} s", flush=True)
    # stage 2: per (family, dm) the 8 best stage-1 (filter, W, ec, y) by R2 net with >= 30 fills
    top = []
    for nm in ("T1", "T1t", "T2", "T3"):
        for dm in E.DMOD:
            rr = [r for r in R1 if r[0] == nm and r[5] == dm and r[9] >= 30]
            rr.sort(key=lambda r: -r[8]); seen = set()
            for r in rr:
                key = (r[1], r[2], r[3], r[4])
                if key in seen: continue
                seen.add(key); top.append((nm, r[1], r[2], r[3], r[4], dm))
                if len(seen) >= 8: break
    R2_ = []
    with get_context("fork").Pool(procs) as p:
        for r in p.imap_unordered(work2, top): R2_ += r
    best = {}
    for nm in ("T1", "T1t", "T2", "T3"):
        for dm in E.DMOD:
            rr = [r for r in R2_ if r[0] == nm and r[5] == dm and r[9] >= 30]
            if not rr: continue
            b = max(rr, key=lambda r: r[8])
            best[f"{nm}|{dm}"] = dict(fam=nm, filt=G["F"][b[1]][1], fi=b[1], W=b[2], end_cre=b[3], y=b[4], dm=dm, size=b[6], ex=b[7],
                                      r2_pnl=b[8], r2_24h=b[8] / h * 24, r2_fills=b[9], r2_per_fill=b[10], r2_att_per_fill=b[11])
    json.dump(dict(best=best, stage1=[list(map(lambda v: v if not isinstance(v, (np.floating, np.integer)) else float(v), r)) for r in R1],
                   stage2=R2_), open(f"{E.C.OUT}/ps6_select.json", "w"), default=float)
    print(f"\nR2 (TRAIN) best per family x queue model (cheap fees, k = {E.KDEF}), {time.time() - t0:.0f} s")
    for k_, b in best.items():
        print(f"  {k_:8s} {b['r2_pnl']:+7.2f} SOL ({b['r2_24h']:+6.2f}/24h) fills {b['r2_fills']:4d} {b['r2_per_fill']:+.4f}/fill att/fill {b['r2_att_per_fill']:6.1f} | "
              f"W {b['W']} endcre {b['end_cre']} y {b['y']} size {b['size']} {b['ex']} {b['filt']}")
