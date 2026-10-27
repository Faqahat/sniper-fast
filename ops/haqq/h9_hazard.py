#!/usr/bin/env python3
# haqq SELL study, step 9: sell hazard per lot-size profile. P(this lot's first sell lands in slot d | not sold before), d = slots
# after the reference (trigger) slot, by the lot's return at the end of slot d-1 (known before slot d). Prints per profile.
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
lots = json.load(open(f"{H.OUT}/lots.json")); P = pickle.load(open(f"{H.OUT}/lotpaths.pkl", "rb"))
prof = lambda sz: {0.25: "A.25", 0.27: "B.27", 0.3: "C.30", 0.4: "D.40", 0.49: "E.49", 0.01: "P.01"}.get(round(sz, 2), "BIG" if sz >= 0.6 else "other")
VB = [(-9, -0.10, "<-10%"), (-0.10, -0.03, "-10..-3"), (-0.03, 0.0, "-3..0"), (0.0, 0.03, "0..3"), (0.03, 0.10, "3..10"), (0.10, 0.25, "10..25"), (0.25, 99, ">25%")]
which = sys.argv[1].split(",") if len(sys.argv) > 1 else ["A.25", "B.27", "C.30", "D.40", "E.49", "P.01"]
for pf in which:
    sel = [p for p in P if prof(lots[p["li"]]["buy"]["sol"]) == pf]
    if not sel: continue
    at = collections.Counter(); sold = collections.Counter(); atd = collections.Counter(); sd = collections.Counter()
    for p in sel:
        f = p["first"]
        for d in range(max(1, p["bslot"] + 1), min(f, p["D"]) + 1):
            v = p["ret_end"][d - 1]
            if np.isnan(v): continue
            vb = next(lab for lo, hi, lab in VB if lo <= v < hi)
            at[(d, vb)] += 1; atd[d] += 1
            if d == f: sold[(d, vb)] += 1; sd[d] += 1
    print(f"\n=== profile {pf}: lots {len(sel)}; first-sell hazard by slot after trigger (rows) x lot return at end of previous slot (cols); n>=15")
    print(f"{'d':>4} {'all':>9} | " + " | ".join(f"{lab:>10}" for _, _, lab in VB))
    for d in list(range(1, 36)) + [39, 40, 41, 45, 49, 50, 51, 56, 57, 58, 59, 60, 61, 64, 65, 66, 100, 101, 102, 200, 201, 202]:
        row = f"{d:>4} {sd[d] / atd[d] if atd[d] else 0:5.0%} {atd[d]:<4d}| " + " | ".join((f"{sold[(d, lab)] / at[(d, lab)]:5.0%} {at[(d, lab)]:<4d}" if at[(d, lab)] >= 15 else f"{'':>10}") for _, _, lab in VB)
        print(row)
