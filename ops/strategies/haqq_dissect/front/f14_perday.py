#!/usr/bin/env python3
"""FRONT step 14 (read-only): per-day robustness of the key numbers (MEASURED). Out: sniper-data/haqq_dissect/front/f14_perday.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
exec(open("/home/moiz/sniper/ops/strategies/haqq_dissect/front/f13_bundle.py").read().split("P(f\"# Bundle-aware")[0])
out2 = []
def Q(*a):
    s = " ".join(str(x) for x in a); print(s); out2.append(s)
Q("| day | paying dumps | bundle-fronted | front #1 pre-sender | reachable-front ms p50 | we attempted | captured | our first landing ms p50 (not captured) | pre-send tries landed next slot |")
Q("|---|---|---|---|---|---|---|---|---|")
O = pickle.load(open(f"{OUT}/f3_ours.pkl", "rb"))
for d in (2, 3, 4, 5, 6):
    g = [r for r in R if r["day"] == d]
    at = [r for r in g if r["st"][0] in "678"]
    cap = sum(r["st"].startswith("8") for r in at)
    om = [r["ourbest"][4] for r in at if r["ourbest"] and not r["st"].startswith("8") and r["ourbest"][4] is not None]
    pr = [F10[r["i"]]["any"] for r in g if r["i"] in F10]
    tt = [t for t in O["tries"] if t.get("slot") is not None and L.day_of(t["t_send"]) == d]
    Q(f"| {L.day_name(d)} | {len(g):,} | {100*np.mean([r['bund'] for r in g]):.1f}% | {100*np.mean(pr):.0f}% | {np.median([r['ms2'] for r in g if r['ms2']<1e8]):.1f} | "
      f"{len(at)} | {cap} ({100*cap/max(len(at),1):.0f}%) | {np.median(om) if om else float('nan'):.0f} | {100*np.mean([t['slot']-t['send_slot']>=1 for t in tt]) if tt else float('nan'):.0f}% |")
open(f"{OUT}/f14_perday.txt", "w").write("\n".join(out2) + "\n")
