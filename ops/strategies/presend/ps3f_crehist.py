#!/usr/bin/env python3
# Causal creator history (an engine can keep this live): for every launch in the 4 tapes, the creator's PREVIOUS launches whose
# outcome was already known at this create (create >= 60 s earlier): count, and how many had an EARLY CREATOR DUMP (creator sell
# moving the price <= -2% within 50 slots of the create). Time-ordered across R1..R4 (deduped by mint; R1 starts with no history).
# -> presend/crehist.json {mint: [n_prev, n_prev_early, first_seen_day]}
import json, collections
import numpy as np
import ps_common as C
L = {}
for day in ("R1", "R2", "R3", "R4"):
    d = C.load(day, cols=("tok", "s", "buy", "uid", "sol", "tokn", "vsol", "vtok", "bt"))
    for t, x in enumerate(d["meta"]):
        if x["m"] in L: continue
        o = int(d["off"][t]); n = int(d["cnt"][t]); sl = slice(o, o + n)
        cre = x.get("creator"); early = False
        if cre:
            u = C.crc(cre)
            m = (d["uid"][sl] == u) & (d["buy"][sl] == 0) & (d["s"][sl] <= x["S0"] + 50) & (d["move"][sl] <= -2.0)
            early = bool(m.any())
        ct = x.get("cbt") or int(d["t"][o])
        L[x["m"]] = (ct, cre, early, day)
order = sorted(L.items(), key=lambda kv: kv[1][0])
hist = collections.defaultdict(list)      # creator -> list of (create time, early)
out = {}
for m, (ct, cre, early, day) in order:
    if cre:
        h = hist[cre]; prev = [e for (t0, e) in h if t0 + 60 <= ct]
        out[m] = [len(prev), int(sum(prev)), day]
        h.append((ct, early))
    else: out[m] = [0, 0, day]
json.dump(out, open(f"{C.OUT}/crehist.json", "w"))
a = np.array([v[:2] for v in out.values()])
for k in (1, 3, 5, 10):
    sel = a[:, 0] >= k
    print(f"launches with >= {k} known previous launches by the creator: {sel.mean():.3f}; of those, prev early-dump rate >= 0.8: {(a[sel, 1] / a[sel, 0] >= 0.8).mean():.3f}")
