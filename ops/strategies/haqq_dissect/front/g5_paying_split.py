#!/usr/bin/env python3
"""FRONT addendum step 5 (read-only, MEASURED): on PAYING dumps in armed windows, the first try after the dump split by
pre-sent (signed before the engine saw the dump) vs signed after; and whether ANY pre-sent try was in flight (sent, landing after
the dump). Out: sniper-data/haqq_dissect/front/g5.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
pc = lambda v, q: float(np.percentile(v, q)) if len(v) else float("nan")
rows = pickle.load(open(f"{OUT}/g2_rows.pkl", "rb")) + pickle.load(open(f"{OUT}/g3_r27_rows.pkl", "rb"))
RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb"))
by = collections.defaultdict(list)
for run, x in RU.items():
    for t in x["tries"]:
        if t.get("slot") is not None and t.get("idx") is not None: by[(run, t["mint"])].append(t)
P("| set | group | dumps with a try after | first try pre-sent | pre-sent: land ms p50 / we were first / filled | signed-after: land ms p50 / first / filled | pre-sent tries landing after the dump (<= 2 slots): mean |")
P("|---|---|---|---|---|---|---|")
for setn, sel in (("paying", lambda r: r["vf"] >= 0.03), ("non-paying >=12%", lambda r: not (r["vf"] >= 0.03) and r["drop"] >= 0.12)):
    for g, f in (("k4", lambda r: r["g"] == "k4 cap20"), ("k8", lambda r: r["g"].startswith("k8"))):
        pre = []; post = []; npre = []
        for r in rows:
            if not (f(r) and sel(r) and "ms" in r): continue
            aft = sorted([t for t in by[(r["run"], r["mint"])] if (t["slot"], t["idx"]) > (r["ds"], r["di"]) and t["slot"] <= r["ds"] + 2], key=lambda t: (t["slot"], t["idx"]))
            if not aft: continue
            isp = lambda t: tuple((t.get("pos") or [0, 0])[:2]) < (r["ds"], r["di"])
            (pre if isp(aft[0]) else post).append(r)
            npre.append(sum(isp(t) for t in aft))
        n = len(pre) + len(post)
        fm = lambda v: f"{pc([r['ms'] for r in v],50):.0f} / {100*np.mean([r['ahead']==0 for r in v]) if v else float('nan'):.0f}% / {100*np.mean([r['ok'] for r in v]) if v else float('nan'):.0f}%"
        P(f"| {setn} | {g} | {n} | {100*len(pre)/max(n,1):.0f}% | {fm(pre)} | {fm(post)} | {np.mean(npre):.2f} |")
open(f"{OUT}/g5.txt", "w").write("\n".join(out) + "\n")
