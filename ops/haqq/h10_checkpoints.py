#!/usr/bin/env python3
# haqq SELL study, step 10: (a) find each profile's checkpoint slots (sell-hazard spikes after the trigger slot);
# (b) at checkpoints, what separates "sold here" from "kept": flow in the window since the previous checkpoint, return, etc.
import sys, json, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
lots = json.load(open(f"{H.OUT}/lots.json")); P = pickle.load(open(f"{H.OUT}/lotpaths.pkl", "rb"))
prof = lambda sz: {0.25: "A.25", 0.27: "B.27", 0.3: "C.30", 0.4: "D.40", 0.49: "E.49", 0.01: "P.01"}.get(round(sz, 2), "BIG" if sz >= 0.6 else "other")
for p in P: p["pf"] = prof(lots[p["li"]]["buy"]["sol"]); p["run"] = lots[p["li"]]["run"]
def hazard(sel, dmax=130):
    at = np.zeros(dmax + 1); sd = np.zeros(dmax + 1)
    for p in sel:
        f = p["first"]
        for d in range(max(1, p["bslot"] + 1), min(f, dmax) + 1):
            at[d] += 1
            if d == f: sd[d] += 1
    return at, sd
CP = {}
for pf in ("A.25", "B.27", "C.30", "D.40", "E.49", "P.01"):
    sel = [p for p in P if p["pf"] == pf]
    at, sd = hazard(sel)
    h = np.where(at >= 30, sd / np.maximum(at, 1), np.nan)
    spikes = []
    for d in range(3, 129):
        nb = [h[x] for x in (d - 3, d - 2, d + 2, d + 3) if 0 < x < len(h) and not np.isnan(h[x])]
        if not np.isnan(h[d]) and nb and h[d] >= 0.06 and h[d] >= 3 * max(np.median(nb), 0.01): spikes.append((d, round(float(h[d]), 2), int(at[d])))
    CP[pf] = spikes
    by_run = collections.Counter(p["run"] for p in sel)
    print(f"{pf} (lots {len(sel)}, by run {dict(sorted(by_run.items()))}): spikes (slot, hazard, at-risk): {spikes}")
json.dump(CP, open(f"{H.OUT}/checkpoints.json", "w"))
