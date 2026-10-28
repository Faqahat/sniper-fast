#!/usr/bin/env python3
"""FRONT step 9 (read-only): pre-send timing vs the dump's position in its block, on paying dumps where pre-send was armed,
and on ALL our live pre-send fills (dv8 live_presend). MEASURED.
Out: sniper-data/haqq_dissect/front/f9_blockpos.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
s0, bsz = L.slot_sizes()
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
rows = pickle.load(open(f"{OUT}/f8_rows.pkl", "rb"))
O = pickle.load(open(f"{OUT}/f3_ours.pkl", "rb"))
T = [t for t in O["tries"] if t.get("slot") is not None and t.get("idx") is not None and 0 <= t["slot"] - s0 < len(bsz)]
fr = np.array([t["idx"] / bsz[t["slot"] - s0] for t in T if t["slot"] == t["send_slot"]])
P("# Pre-send timing (MEASURED, live tries AMS16-33 + FRA21-26)")
P(f"- tries {len(T):,}; landed in the engine's send slot {100*len(fr)/len(T):.0f}%, next slot {100*np.mean([t['slot']-t['send_slot']==1 for t in T]):.0f}%, later "
  f"{100*np.mean([t['slot']-t['send_slot']>=2 for t in T]):.0f}%")
P(f"- block position (tx index / block size) of tries landing in their send slot: p10 {np.percentile(fr,10):.2f}, p25 {np.percentile(fr,25):.2f}, p50 {np.median(fr):.2f}, p75 {np.percentile(fr,75):.2f}")
c = collections.Counter((t["run"], t["mint"], t["send_slot"]) for t in O["tries"]); v = np.array(list(c.values()))
P(f"- tries per armed slot: p50 {np.median(v):.0f}, mean {v.mean():.2f}")
# armed paying dumps: by dump block position
A = [r for r in rows if r.get("armed") and r["st"].startswith(("6", "8"))]
P(f"\n## Paying dumps where pre-send was armed: {len(A):,}, by the dump's position in its block")
P("| dump block position | dumps | a try landed in the dump slot after it | our first after-dump try: buys ahead p50 | we were first & filled | front value SOL (sum) |")
P("|---|---|---|---|---|---|")
for lo, hi in ((0, .25), (.25, .5), (.5, .75), (.75, 1.01)):
    g = [r for r in A if lo <= r["di"] / bsz[r["ds"] - s0] < hi]
    if not g: continue
    sa = [r for r in g if any(t["slot"] == r["ds"] and t["rel"] == "same" for t in r["tries"])]
    ah = [r["ourbest"][3] for r in g if r["ourbest"]]
    P(f"| {lo:.2f}-{min(hi,1):.2f} | {len(g)} | {100*len(sa)/len(g):.0f}% | {np.median(ah) if ah else float('nan'):.0f} | {sum(r['st'].startswith('8') for r in g)} | {sum(r['v'] for r in g):+.1f} |")
# all live pre-send fills (dv8 live_presend: res ok, tape known): dump position and our position
PR = [p for p in pickle.load(open(f"{L.D}/live_presend.pkl", "rb")) if p.get("res") == "ok" and p.get("dslot") is not None and p.get("didx") is not None]
d = np.array([p["didx"] / bsz[p["dslot"] - s0] for p in PR if 0 <= p["dslot"] - s0 < len(bsz)])
P(f"\n## All live pre-send FILLS (n {len(d):,}): block position of the dump they followed p25/p50/p75 {np.percentile(d,25):.2f}/{np.median(d):.2f}/{np.percentile(d,75):.2f} "
  f"(paying dumps overall: {np.percentile([r['di']/bsz[r['ds']-s0] for r in rows],25):.2f}/{np.median([r['di']/bsz[r['ds']-s0] for r in rows]):.2f}/{np.percentile([r['di']/bsz[r['ds']-s0] for r in rows],75):.2f})")
open(f"{OUT}/f9_blockpos.txt", "w").write("\n".join(out) + "\n")
