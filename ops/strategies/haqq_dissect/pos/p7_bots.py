#!/usr/bin/env python3
"""pos step 7 (read-only): what triggers each of haqq's sub-bots (code), and how its lots do as the FIRST lot in a trip vs as an ADD
(another bot already holds). Context MEASURED from the tape before each buy (p1). Code-matched P&L. Out: p7.txt"""
import collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import *
P = Out(f"{OUT}/p7.txt")
B, LO, T = load()
ok = lambda t: not t["mayhem"] and not t["gap"]
LG = [l for l in LO if ok(T[l["trip_ix"]]) and l["code"] is not None and not l["probe"]]
P("# haqq sub-bots: entry context (medians / shares) and P&L as first lot vs add (code-matched; all days)")
P("| code | role | lots | net SOL | mean mSOL | win | dump <=2 slots before (>=5%) | dump drop p50 | dd10 p50 | age p50 s | curve SOL p50 | outside flow 3 slots p50 | slots after prev buy p50 | price vs prev buy p50 |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in (248, 247, 244, 226, 231, 251, 234):
    for role, f in (("first", lambda l: l["kbuy"] == 1), ("add", lambda l: l["kbuy"] > 1)):
        v = [l for l in LG if l["code"] == c and f(l)]
        if len(v) < 20: continue
        b = [B[l["b"]] for l in v]; x = [l["cnet"] for l in v]
        dmp = [bb["d_drop"] >= 0.05 and (bb["d_slots"] if bb["d_slots"] is not None else 99) <= 2 for bb in b]
        md = lambda a: np.median([y for y in a if y is not None]) if any(y is not None for y in a) else float("nan")
        P(f"| {c} | {role} | {len(v):,} | {sum(x):+.2f} | {1000 * np.mean(x):+.2f} | {100 * np.mean([y > 0 for y in x]):.0f}% | {100 * np.mean(dmp):.0f}% | "
          f"{100 * md([bb['d_drop'] for bb in b]):.0f}% | {100 * md([bb['dd10'] for bb in b]):.0f}% | {0.212 * md([bb['age'] for bb in b]):.1f} | {md([bb['vsol_pre'] for bb in b]):.0f} | "
          f"{md([bb['bo3'] - bb['so3'] for bb in b]):+.2f} | {md([bb['dt_prev_slots'] for bb in b]):.0f} | {100 * md([bb['px_vs_prev'] for bb in b]):+.1f}% |")
# which code buys after which (adds): transition matrix (prev buy code -> add code), with add mean P&L
P("\n## Adds: previous buy's code -> this add's code (count, add mean mSOL)")
tr = collections.defaultdict(list)
byt = collections.defaultdict(list)
for l in LG: byt[l["trip_ix"]].append(l)
for ti, v in byt.items():
    v.sort(key=lambda l: l["cc"])
    for a, b_ in zip(v, v[1:]): tr[(a["code"], b_["code"])].append(b_["cnet"])
P("| prev -> add | adds | mean mSOL | net SOL |"); P("|---|---|---|---|")
for k, v in sorted(tr.items(), key=lambda kv: -len(kv[1]))[:16]:
    P(f"| {k[0]} -> {k[1]} | {len(v):,} | {1000 * np.mean(v):+.2f} | {sum(v):+.2f} |")
P.save()
