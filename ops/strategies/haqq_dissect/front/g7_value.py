#!/usr/bin/env python3
"""FRONT addendum step 7 (read-only): value split of paying dumps in armed windows (arm-slot dumps vs covered) and the live k8 uplift
converted to SOL (INFERRED: calibrated 0.61 x front value - 1.17 - 2.01 mSOL per capture). Out: sniper-data/haqq_dissect/front/g7.txt"""
import pickle, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
rows = pickle.load(open(f"{OUT}/g2_rows.pkl", "rb")) + pickle.load(open(f"{OUT}/g3_r27_rows.pkl", "rb"))
RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb"))
by = collections.defaultdict(list)
for run, x in RU.items():
    for t in x["tries"]: by[(run, t["mint"])].append(t)
H = {"k4": sum((x["t1"] - x["t0"]) / 3600 for r, x in RU.items() if x["cfg"]["k"] == 4), "k8": sum((x["t1"] - x["t0"]) / 3600 for r, x in RU.items() if x["cfg"]["k"] == 8)}
rng = np.random.default_rng(9)
res = {}
for g, f in (("k4", lambda r: r["g"] == "k4 cap20"), ("k8", lambda r: r["g"].startswith("k8"))):
    cov = []; arm = []
    for r in rows:
        if not (f(r) and r["vf"] >= 0.03 and "ms" in r): continue
        aft = [t for t in by[(r["run"], r["mint"])] if t.get("slot") is not None and t.get("idx") is not None and (t["slot"], t["idx"]) > (r["ds"], r["di"]) and t["slot"] <= r["ds"] + 2]
        pre = [t for t in aft if tuple((t.get("pos") or [0, 0])[:2]) < (r["ds"], r["di"])]
        (cov if pre else arm).append(r)
    net = lambda v: 0.61 * v * 1000 - 1.17 - 2.01
    res[g] = (cov, arm)
    P(f"{g}: {H[g]:.1f} engine-h; paying dumps with a try after: covered by a pre-sent try {len(cov)} ({len(cov)/H[g]:.1f}/h, front value {sum(r['vf'] for r in cov):.1f} SOL), "
      f"not covered (dump in/next to the arm slot) {len(arm)} ({len(arm)/H[g]:.1f}/h, front value {sum(r['vf'] for r in arm):.1f} SOL); "
      f"covered: we were first {100*np.mean([r['ahead']==0 for r in cov]):.0f}%, mean calibrated net per capture {np.mean([net(r['vf']) for r in cov]):.1f} mSOL")
c4, c8 = res["k4"][0], res["k8"][0]
f4 = np.array([r["ahead"] == 0 for r in c4], float); f8 = np.array([r["ahead"] == 0 for r in c8], float)
d = [rng.choice(f8, len(f8)).mean() - rng.choice(f4, len(f4)).mean() for _ in range(2000)]
P(f"k8 - k4 'we were first' on covered paying dumps: {100*(f8.mean()-f4.mean()):+.1f} pts [90%: {100*np.percentile(d,5):+.1f}..{100*np.percentile(d,95):+.1f}]")
netv = np.mean([0.61 * r["vf"] * 1000 - 1.17 - 2.01 for r in c4])
rate = len(c4) / H["k4"]
for dp in (np.percentile(d, 5), f8.mean() - f4.mean(), np.percentile(d, 95)):
    P(f"  uplift {100*dp:+.1f} pts x {rate:.1f} covered paying dumps/h x {netv:.1f} mSOL = {dp*rate*netv/1000:+.3f} SOL/h = {24*dp*rate*netv/1000:+.2f} SOL/day at 24 h")
open(f"{OUT}/g7.txt", "w").write("\n".join(out) + "\n")
