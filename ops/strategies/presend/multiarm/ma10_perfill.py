#!/usr/bin/env python3
"""MULTIARM: per-fill economics of the EXTRA windows of each variant vs the base's own re-arm fills (pooled over reps):
fill rate of the extra windows, mean cash per extra fill (slip / -20% / raw, mSOL), mean failed tries per extra window.
usage: ma10_perfill.py RUNDIR OUT.json [--base R0]"""
import sys, json, glob, pickle, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
from ma7_tables import load, key_of


def main(rundir, outp, base="R0"):
    V = load(rundir)
    out = {}
    for name in sorted(V):
        reps = sorted(set(V[name]) & set(V[base]))
        ew = ef = 0; cs = []; cc = []; cr = []; fl = []; bc = []; bcc = []
        for rep in reps:
            A = V[name][rep]["rows"]; B = V[base][rep]["rows"]
            bk = {key_of(r) for r in B}
            for r in A:
                if key_of(r) in bk: continue
                ew += 1; fl.append(r["fails"])
                if r["filled"]: ef += 1; cs.append(r["cash"] + r["fails"] * 5120e-9); cc.append(r["cash_cut"] + r["fails"] * 5120e-9); cr.append(r["cash_naive"] + r["fails"] * 5120e-9)
            if name == base:
                for r in A:
                    if r["kind"] == "rearm" and r["filled"]: bc.append(r["cash"] + r["fails"] * 5120e-9); bcc.append(r["cash_cut"] + r["fails"] * 5120e-9)
        d = {"extra_windows": ew / max(len(reps), 1), "extra_fill_rate": ef / max(ew, 1), "fails_per_extra_window": float(np.mean(fl)) if fl else None,
             "extra_fill_mSOL_slip": 1e3 * float(np.mean(cs)) if cs else None, "extra_fill_mSOL_cut": 1e3 * float(np.mean(cc)) if cc else None,
             "extra_fill_mSOL_raw": 1e3 * float(np.mean(cr)) if cr else None, "extra_fill_median_mSOL_slip": 1e3 * float(np.median(cs)) if cs else None,
             "extra_fill_win_share": float(np.mean(np.array(cs) > 0)) if cs else None}
        if name == base: d.update({"base_rearm_fill_mSOL_slip": 1e3 * float(np.mean(bc)), "base_rearm_fill_mSOL_cut": 1e3 * float(np.mean(bcc)),
                                   "base_rearm_fill_win_share": float(np.mean(np.array(bc) > 0))})
        out[name] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}
    json.dump(out, open(outp, "w"), indent=1)
    for k, v in out.items(): print(k.ljust(14), v)


if __name__ == "__main__":
    a = sys.argv[1:]
    base = "R0"
    if "--base" in a: i = a.index("--base"); base = a[i + 1]; del a[i:i + 2]
    main(a[0], a[1], base)
