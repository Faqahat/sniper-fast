#!/usr/bin/env python3
"""8yYMhu o3 (read-only): on the dumps we FILLED with pre-send, did 8yYMhu also try (any on-chain attempt with the same trigger), and
what happened to his attempt (landed / band / slip / late)? Our fill lifts the curve; his band upper bound is ~1.04x the post-dump vSOL.
Out: DATA/o3.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
H = pickle.load(open(f"{X.D}/h2h.pkl", "rb")); A = pickle.load(open(f"{X.D}/att.pkl", "rb"))
by = collections.defaultdict(list)
for a in A:
    if "trig_slot" in a: by[(a["mint"], a["trig_slot"], a["trig_idx"])].append(a)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
T_ = [h for h in H if h.get("tape") and h.get("dump_slot") is not None]
c = collections.Counter(); ex = collections.defaultdict(list)
for h in T_:
    v = by.get((h["mint"], h["dump_slot"], h["dump_idx"]), [])
    if not v: c["he did not try"] += 1; continue
    o = "+".join(sorted(set(a["out"] for a in v)))
    first = min(v, key=lambda a: (a["s"], a["i"]))
    ahead = (first["s"], first["i"]) < (h["s"], h["i"])
    c[f"he tried: {o} ({'his copy landed before ours' if ahead else 'ours first'})"] += 1
    ex[o].append((h, first))
P(f"our pre-send fills on tape with an identified dump: {len(T_)}")
for k, n in c.most_common(): P(f"   {n:4}  {k}")
for o, v in ex.items():
    for h, a in v[:3]:
        P(f"   e.g. [{o}] [{h['mint'][:8]}]({X.gm(h['mint'])}) our fill [{h['buy_sig'][:8]}]({X.ss(h['buy_sig'])}) idx {h['i']} | his attempt [{a['sig'][:8]}]({X.ss(a['sig'])}) slot {a['s']} idx {a['i']} ({a['out']})")
open(f"{X.D}/o3.txt", "w").write("\n".join(out) + "\n")
