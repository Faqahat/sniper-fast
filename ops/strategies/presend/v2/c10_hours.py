#!/usr/bin/env python3
# PRE-SEND V2 step c10: hour-to-hour spread of the finalists (all 4 days) -> how many live hours a run needs before its total is
# above zero with ~90% probability (normal approximation on clock-hour sums; INFERRED planning number).
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {d: E.load(d) for d in V.DAYS}
F = json.load(open(f"{V.OUT}/finalists.json")); F.update(json.load(open(f"{V.OUT}/finalists_h6.json")))
out = {}
for name in ("P1_as_run_0.2_k4", "A_k4_0.55", "B_k8_0.55", "C_k8_1.0", "D_k12_1.0", "A6_k4_0.55", "B6_k8_0.55", "C6_k8_1.0", "D6_k12_1.0", "A6_k4_1.0"):
    r = R.ev(F[name], V.DAYS, detail=True)
    h = np.concatenate([r[d]["hourly"] for d in V.DAYS])
    mu, sd = h.mean(), h.std(ddof=1)
    need = (1.2816 * sd / mu) ** 2 if mu > 0 else float("inf")
    out[name] = dict(mu=mu, sd=sd, hours=len(h), need90=need, p_pos_1h=float((h > 0).mean()))
    print(f"{name:18s} per clock hour: mean {mu:+.3f} SOL, sd {sd:.3f}, positive {100 * (h > 0).mean():.0f}% of {len(h)} h | hours for P(total > 0) ~90%: {need:.1f}")
json.dump(out, open(f"{V.OUT}/c10_hours.json", "w"), default=float)
