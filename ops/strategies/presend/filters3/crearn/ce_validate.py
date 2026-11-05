#!/usr/bin/env python3
"""check the baseline replay against what the live engine did in r47–r50: same blocks, same (n, sum) at each arm / skip"""
import sys, collections, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/crearn")
import ce_lib as L, ce_sim as S
W = L.windows(); SF = S.seed_full()
log = []
out, led = S.run(W, {"resolve": True}, SF, log)
pickle.dump(W, open(f"{L.D0}/windows.pkl", "wb"))
st = collections.Counter(); bad = []
for (w, dec, val), lg in zip(out, [None] * len(out)):
    if w["run"] not in L.GATE_RUNS: continue
    live_dec = "block" if w["live"] is None else "trade"
    st[(w["kind"], live_dec, dec)] += 1
    if live_dec != dec: bad.append((w["run"], w["kind"], w["creator"], live_dec, dec, w.get("arm_cr")))
print("r47–r50 live vs replay decision:", dict(st))
print("unresolved creator skips:", sum(1 for w in W if w["live"] is None and not w["creator"]), "resolved:", sum(1 for w in W if w.get("resolved")))
for b in bad[:20]: print("  MISMATCH", b)
# (n, sum) at arm vs logged
mm = 0; tot = 0; ex = []
i = 0
for (w, dec, val) in out:
    pass
