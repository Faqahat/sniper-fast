#!/usr/bin/env python3
# PRE-SEND V2: causal creator history over R1, R2, R3 and the FULL R4 tape (the study's crehist only had R4's first 3.3 h).
# For every launch: the creator's PREVIOUS launches whose outcome was known at this create (create >= 60 s earlier): count,
# how many had an early creator dump (the study's rule: a creator sell moving the price <= -2% within 50 slots of the create),
# and how many had a BIG early creator dump (<= -8% within 60 slots, the pre-senders' target). Time-ordered across the days.
# -> presend_v2/crehist_v2.json {mint: [n_prev, n_prev_early, n_prev_big, day]}
import sys, os, json, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
L = {}
for day in [d for d in ("R1", "R2", "R3", "R4", "R5") if os.path.exists(V.TAPE[d] + ".npz")]:
    d = V.load_day(day, cols=("tok", "s", "buy", "uid", "sol", "tokn", "vsol", "vtok", "bt"))
    for t, x in enumerate(d["meta"]):
        if x["m"] in L: continue
        o = int(d["off"][t]); n = int(d["cnt"][t]); sl = slice(o, o + n)
        cre = x.get("creator"); early = big = False
        if cre:
            u = V.crc(cre)
            cs = (d["uid"][sl] == u) & (d["buy"][sl] == 0)
            early = bool((cs & (d["s"][sl] <= x["S0"] + 50) & (d["move"][sl] <= -2.0)).any())
            big = bool((cs & (d["s"][sl] <= x["S0"] + 60) & (d["move"][sl] <= -8.0)).any())
        ct = x.get("cbt") or int(d["t"][o])
        L[x["m"]] = (ct, cre, early, big, day)
order = sorted(L.items(), key=lambda kv: kv[1][0])
hist = collections.defaultdict(list)
out = {}
for m, (ct, cre, early, big, day) in order:
    if cre:
        h = hist[cre]; prev = [(e, b) for (t0, e, b) in h if t0 + 60 <= ct]
        out[m] = [len(prev), int(sum(e for e, _ in prev)), int(sum(b for _, b in prev)), day]
        h.append((ct, early, big))
    else: out[m] = [0, 0, 0, day]
json.dump(out, open(f"{V.OUT}/crehist_v2.json", "w"))
a = np.array([v[:3] for v in out.values()], float)
print(f"launches {len(out)}")
for k in (1, 3, 5, 10):
    sel = a[:, 0] >= k
    print(f"  >= {k} known previous launches: {sel.mean():.3f}; of those prev early-dump rate >= 0.8: {(a[sel, 1] / a[sel, 0] >= 0.8).mean():.3f}, "
          f"big-dump rate >= 0.8: {(a[sel, 2] / a[sel, 0] >= 0.8).mean():.3f}")
