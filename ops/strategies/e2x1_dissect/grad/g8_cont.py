#!/usr/bin/env python3
"""grad agent, step 8: tape-wide completeness test of the recorded PumpSwap events.
Base-token pool reserves are exact integers that only trades (and rare liquidity deposits/withdrawals) change. For each pair of
consecutive recorded events in a pool, the reserve after event e must equal the reserve before event e+1. A missing trade shows as a
break. Also checks the first event against the migration's opening reserves. Window: migration .. +566 slots (2 min) and +1500."""
import numpy as np, collections
from glib import Tape, pday

T = Tape()
out = collections.defaultdict(lambda: [0, 0, 0, 0])     # day -> [pairs, breaks, first_ok, first_n]
gap_tok = []
for m, mg in T.mig.items():
    if not mg["quote"].startswith("So111"): continue
    cr = T.cr.get(m)
    if cr is None or cr.get("mayhem"): continue
    P = T.pool_events(mg["pool"])
    P = P[P["slot"] <= mg["slot"] + 566]
    d = pday(mg["bt"]); o = out[d]
    if len(P):
        o[3] += 1; o[2] += int(P["pbase"][0] == mg["pbase"])
    if len(P) < 2: continue
    B = P["pbase"].astype(np.int64); b = P["base"].astype(np.int64)
    post = np.where(P["buy"] == 1, B - b, B + b)
    ok = post[:-1] == B[1:]
    o[0] += len(ok); o[1] += int((~ok).sum())
    gap_tok += list((np.abs(post[:-1] - B[1:]) / np.maximum(B[1:], 1))[~ok])
print("day    pairs   breaks  break%  first-event-matches-opening")
tp = tb = 0
for d in sorted(out):
    p, b, fo, fn = out[d]; tp += p; tb += b
    print(f"{d}  {p:7d}  {b:6d}  {b / max(p, 1):6.2%}  {fo}/{fn}")
print(f"ALL    {tp:7d}  {tb:6d}  {tb / max(tp, 1):6.2%}")
if gap_tok: print("break size (share of pool base): median", np.median(gap_tok), "p90", np.percentile(gap_tok, 90))
