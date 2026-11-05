#!/usr/bin/env python3
"""SMARTEXIT step 6: is the decision->land lag a function of the decision's phase in the slot?  (all runs, real time-ms exits)
phase = decision rx t - first-seen rx t of the latest slot seen before the decision (slotmap).  Prints lag by phase bin + slot length.
Used to build the phase-conditioned lag resample (slib.phase_lag) -- a robustness row, not tuning."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L
SM = {int(k): v[0] for k, v in json.load(open(f"{L.D}/slotmap.json")).items()}
F, J, _ = L.load_fills()
def cur_slot(f, d):
    best = None
    for s in range(f.x["slot"] - 1, f.x["slot"] + 17):
        if s in SM and SM[s] <= d: best = s
    return best
B = collections.defaultdict(list); dS = collections.defaultdict(collections.Counter); slen = []
for f in F:
    for s in range(f.x["slot"], f.x["slot"] + 6):
        if s in SM and s + 1 in SM: slen.append((SM[s + 1] - SM[s]) / 1e6)
    ex = f.x["exit"]
    if ex["why"] != "time-ms": continue
    d = ex["t"]; s = cur_slot(f, d)
    if s is None: continue
    ph = (d - SM[s]) / 1e6
    b = min(int(ph // 25), 12)
    B[(f.split, b)].append(f.lag); dS[b][f.x["sells"][0]["slot"] - s] += 1
print("slot length ms p10/25/50/75/90:", [round(L.pct(slen, p)) for p in (.1, .25, .5, .75, .9)], "n", len(slen))
for sp in ("dev", "val", "hold"):
    print(f"== {sp}: lag by decision phase (25 ms bins)")
    for b in range(13):
        v = B.get((sp, b), [])
        if len(v) >= 10: print(f"  phase {b * 25:3}-{b * 25 + 25:3}: n {len(v):4} lag p25/50/75/90 {[round(L.pct(v, p)) for p in (.25, .5, .75, .9)]}  dslot {dict(sorted(dS[b].items()))}")
