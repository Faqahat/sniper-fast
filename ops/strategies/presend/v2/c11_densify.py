#!/usr/bin/env python3
# PRE-SEND V2 step c11: the other bound for more attempts per slot. Consecutive probe attempts have strongly CORRELATED send -> seen
# times (MEASURED: corr 0.77 between neighbours, landing order inverted in only 6.9% of pairs), so the iid model (c3) may overstate
# the gain. Here each probe window's REAL attempt stream is densified: m - 1 extra attempts between every two real ones, each taking
# the send -> seen time and the deadline outcome of the real attempt before it (= fully correlated with its neighbour). Per dump,
# the first attempt that could fill (signed before we saw the dump, landing after it, not a deadline failure), as in c2.
# Only the probe's first sighting clock is available for the synthetic copies; the probe's real D is shown on the same clock.
import json, collections
import numpy as np
F = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
att = {}; land = {}
for l in open(F):
    if '"presend_attempt' not in l: continue
    o = json.loads(l)
    if o["ev"] == "presend_attempt": att[o["sig"]] = o
    else: land[o["sig"]] = o
byw = collections.defaultdict(list)
for s, a in att.items():
    l = land.get(s); ok = bool(l and l.get("res") != "unseen" and l.get("first_rx"))
    byw[a["w"]].append(dict(n=a["n"], ts=a["t"] / 1e6, R=(l["first_rx"] / 1e6 - a["t"] / 1e6) if ok else np.inf, dl=(not ok) or l["res"] == "deadline"))
for w in byw: byw[w].sort(key=lambda r: r["n"])
dumps = {}
for l in land.values():
    d = l.get("d")
    if d and d.get("a"): dumps[(l["w"], d["slot"], d["idx"])] = d
out = {}
for m in (1, 2, 3, 5):
    Ds = []; none = 0
    for (w, s, i), d in dumps.items():
        seen = d.get("first_rx", d["t"]) / 1e6
        A = byw[w]; S = []
        for a, b in zip(A, A[1:] + [None]):
            S.append((a["ts"], a["R"], a["dl"]))
            if b is not None:
                for j in range(1, m): S.append((a["ts"] + (b["ts"] - a["ts"]) * j / m, a["R"], a["dl"]))
        c = [t + R for t, R, dl in S if t < seen and t + R > seen and not dl]
        if c: Ds.append(min(c) - seen)
        else: none += 1
    k = 3.79 * m
    out[m] = dict(k=k, none=none / len(dumps), q=[float(np.percentile(Ds, p)) for p in (10, 25, 50, 75, 90)])
    print(f"k {k:5.2f} (fully correlated copies): no attempt could fill {100 * none / len(dumps):4.1f}% | D on the first sighting clock p10/p25/p50/p75/p90 "
          + " / ".join(f"{x:5.1f}" for x in out[m]["q"]))
json.dump(out, open("/home/moiz/sniper-data/presend_v2/c11_densify.json", "w"))
