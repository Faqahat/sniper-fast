#!/usr/bin/env python3
"""APEX-REALISM r0: export APEX-3 walk-forward picks (watchlist sel + entry score + q0.5 threshold per day) and the sim
values already stored (pos A/R1/R2/R3 at 0.4/1.0, exits h2 & w0.4_6.0, phi 0/0.2) for cross-checking.
Uses the apexcmp copy of APEX-3 code (res = APEX-3 days 0-6 + day 7 extended to 11-04 00:45 PKT)."""
import sys, json, pickle, numpy as np
sys.path.insert(0, "/home/it/sniper-studies/sniper-apexcmp/code")
import run3_lib as R3
from ev3 import PI, XI
L, day, sel, score, RUNS, HRS = R3.L, R3.day, R3.sel, R3.score, R3.RUNS, R3.HRS
thr = {d: float(np.nanquantile(score[(day == d - 1) & sel], 0.5)) for d in range(2, len(RUNS))}
out = dict(runs=RUNS, hrs=HRS, thr=thr, picks=[])
for i, r in enumerate(L):
    if not sel[i]: continue
    R = r[6]
    v = {f"{p}_{z}_{h}_{e}": float(R[PI[p], zi, hi, XI[e]]) for p in ("A", "R1", "R2", "R3", "E", "N") for zi, z in ((1, "0.4"), (2, "1.0"))
         for hi, h in ((0, "0"), (1, "0.2")) for e in ("h2", "w0.4_6.0")}
    out["picks"].append(dict(mint=r[0], creator=r[1], bt=int(r[2]), cs=int(r[3]), ci=int(r[4]), day=int(day[i]), run=RUNS[day[i]],
                             score=float(score[i]) if np.isfinite(score[i]) else None, ncs=r[5]["ncs"], nb=r[5]["nb"], u=r[5]["u"], v=v))
json.dump(out, open("/home/it/sniper-data/apex2/realism/picks.json", "w"))
print("picks", len(out["picks"]), "per day", np.bincount([p["day"] for p in out["picks"]]), "thr", {k: round(v, 3) for k, v in thr.items()}, "hrs", np.round(HRS, 2))
