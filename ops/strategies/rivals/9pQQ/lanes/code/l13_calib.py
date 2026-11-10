#!/usr/bin/env python3
"""LANES step 13: sim calibration: replay 9pQQ's own trips at its own times (9pQQ removed) and compare with its real net (rent excluded,
curve-sold trips only); then its picks+exit at +70 ms (info row) and -20% followers. Per module NEW/TRK. -> lanes/calib.json"""
import sys, json, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import sim, tlib
out = {}
for run in tlib.RUNS:
    T = sim.Tape(run); t = T.t; R = tlib.trips(run); hrs = tlib.hours(run)
    real, mod_, res = [], [], {k: [] for k in ("its", "its_fol20", "its70", "its70_fol20")}
    for r in R:
        if r["amm_exit"] or r["mint"] not in t.mix: continue
        m = t.mix[r["mint"]]; a, b = t.ms[m], t.ms[m + 1]
        key = t.s[a:b].astype(np.int64) * 100000 + t.i[a:b]
        jb = a + int(np.searchsorted(key, r["bs"] * 100000 + r["bi"])); js = a + int(np.searchsorted(key, r["ss"] * 100000 + r["si"]))
        if js >= b or t.u[js] != t.wid: continue
        size = 0.48e9 if r["spend"] < 600e6 else 0.7e9
        tb, ts = T.cc[jb] - 1e-6, T.cc[js] - 1e-6
        res["its"].append(T.trip(m, tb, ts, size=size)); res["its_fol20"].append(T.trip(m, tb, ts, fol=0.2, size=size))
        # trigger = last outside row before its buy
        j = jb - 1
        while j >= a and t.u[j] == t.wid: j -= 1
        trig = T.cc[j] if j >= a else tb
        res["its70"].append(T.trip(m, trig + 70, ts + 25, size=size)); res["its70_fol20"].append(T.trip(m, trig + 70, ts + 25, fol=0.2, size=size))
        real.append(r["net"] - (r.get("rent", 0) or 0)); mod_.append(0 if (r["k_prev"] == 0 or r["since_sell"] > 20000) else 1)
    mod_ = np.array(mod_); real = np.array(real) * 1e9
    d = {"n": len(real), "real_rent_incl": round(sum(r["net"] for r in R) * 24 / hrs, 2), "corr_its_vs_real": round(float(np.corrcoef(real, res["its"])[0, 1]), 4)}
    for k, v in res.items():
        v = np.array(v)
        d[k] = {nm: round(float(v[sel].sum() / 1e9 * 24 / hrs), 2) for nm, sel in (("all", mod_ >= 0), ("NEW", mod_ == 0), ("TRK", mod_ == 1))}
    d["real_sim_set"] = {nm: round(float(real[sel].sum() / 1e9 * 24 / hrs), 2) for nm, sel in (("all", mod_ >= 0), ("NEW", mod_ == 0), ("TRK", mod_ == 1))}
    out[tlib.DAY[run]] = d; print(tlib.DAY[run], json.dumps(d), flush=True)
    del T
json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/calib.json", "w"), indent=1)
