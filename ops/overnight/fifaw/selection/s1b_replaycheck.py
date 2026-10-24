#!/usr/bin/env python3
# read-only: why does a plain constant-product replay of the recorded trades miss the recorded curve state on ~21% of
# trades? check k = vsol*vtok constancy, mismatch sizes, buy vs sell, trade sizes
import sys, json, gzip, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/fifaw/selection")
from s1_build import read_mints
L = rp.load_launches()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
ms = list(A)[:60]
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
TR = {}
for (run, b), s in byb.items(): TR.update(read_mints((run, b, s)))
errs = collections.Counter(); kdev = []; ex = []
for m, tr in TR.items():
    st = rp.structure(tr, L[m]); gi = st["g_end"]
    if gi == 0 or not tr[gi - 1]["vtok"] or not tr[gi - 1]["vsol"]: continue
    k0 = tr[gi - 1]["vsol"] * tr[gi - 1]["vtok"]
    prev = tr[gi - 1]
    for t in tr[gi:]:
        if not t["vsol"]: break
        kdev.append(t["vsol"] * t["vtok"] / k0 - 1)
        V, T = prev["vsol"], prev["vtok"]
        if t["buy"]: dd = T * t["sol"] // (V + t["sol"]); V2 = V + t["sol"]; T2 = T - dd; dv_rec = t["vsol"] - prev["vsol"]
        else: so = V * t["tok"] // (T + t["tok"]); V2 = V - so; T2 = T + t["tok"]; dv_rec = t["vsol"] - prev["vsol"]
        rel = abs(V2 / t["vsol"] - 1)
        key = ("buy" if t["buy"] else "sell", "ok" if rel < 1e-6 else ("small" if rel < 1e-3 else "big"))
        errs[key] += 1
        if key[1] == "big" and len(ex) < 8: ex.append((m[:6], t["s"] - L[m]["slot"], t["i"], t["j"], t["buy"], t["sol"], dv_rec, t["tok"], T - t["vtok"] if t["buy"] else t["vtok"] - T, t["user"][:6]))
        prev = t
print(errs)
kdev.sort(); n = len(kdev)
print("k deviation quantiles", [f"{kdev[int(q*(n-1))]:.2e}" for q in (0, .01, .1, .5, .9, .99, 1)])
for e in ex: print(e)
