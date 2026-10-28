#!/usr/bin/env python3
"""FRONT addendum step 6 (read-only, MEASURED): paying dumps with NO pre-sent try landing after them - why? Dump distance from the
window's arm slot; tries SENT in the 2 slots up to the dump; tries that landed BEFORE the dump in its slot / the slot before.
Out: sniper-data/haqq_dissect/front/g6.txt"""
import pickle, collections, sys
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
pc = lambda v, q: float(np.percentile(v, q)) if len(v) else float("nan")
rows = pickle.load(open(f"{OUT}/g2_rows.pkl", "rb")) + pickle.load(open(f"{OUT}/g3_r27_rows.pkl", "rb"))
RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb"))
by = collections.defaultdict(list); arms = collections.defaultdict(list)
for run, x in RU.items():
    for t in x["tries"]: by[(run, t["mint"])].append(t)
    for a in x["arms"]: arms[(run, a["mint"])].append(a)
P("| set | group | class | dumps | dump slots after arm p25/p50/p75 | dump in arm slot or +1 | tries sent in [dump-2, dump] p50 | none sent | a try landed before the dump (same/prev slot) |")
P("|---|---|---|---|---|---|---|---|---|")
for setn, sel in (("paying", lambda r: r["vf"] >= 0.03), ("non-paying >=12%", lambda r: not (r["vf"] >= 0.03) and r["drop"] >= 0.12)):
    for g, f in (("k4", lambda r: r["g"] == "k4 cap20"), ("k8", lambda r: r["g"].startswith("k8"))):
        C = collections.defaultdict(list)
        for r in rows:
            if not (f(r) and sel(r)): continue
            T = by[(r["run"], r["mint"])]
            aft = [t for t in T if t.get("slot") is not None and t.get("idx") is not None and (t["slot"], t["idx"]) > (r["ds"], r["di"]) and t["slot"] <= r["ds"] + 2]
            pre_aft = [t for t in aft if tuple((t.get("pos") or [0, 0])[:2]) < (r["ds"], r["di"])]
            cls = "pre-sent try landed after" if pre_aft else "NO pre-sent try after"
            a = [a for a in arms[(r["run"], r["mint"])] if a["arm_slot"] is not None and a["arm_slot"] <= r["ds"]]
            da = r["ds"] - max(x["arm_slot"] for x in a) if a else None
            sent = sum(1 for t in T if r["ds"] - 2 <= (t.get("send_slot") or -9) <= r["ds"])
            bef = any(t.get("slot") is not None and t.get("idx") is not None and (t["slot"], t["idx"]) < (r["ds"], r["di"]) and t["slot"] >= r["ds"] - 1 for t in T)
            C[cls].append((da, sent, bef))
        for cls, v in sorted(C.items()):
            da = [x[0] for x in v if x[0] is not None]
            P(f"| {setn} | {g} | {cls} | {len(v)} | {pc(da,25):.0f}/{pc(da,50):.0f}/{pc(da,75):.0f} | {100*np.mean([d<=1 for d in da]):.0f}% | {pc([x[1] for x in v],50):.0f} | "
              f"{100*np.mean([x[1]==0 for x in v]):.0f}% | {100*np.mean([x[2] for x in v]):.0f}% |")
open(f"{OUT}/g6.txt", "w").write("\n".join(out) + "\n")
