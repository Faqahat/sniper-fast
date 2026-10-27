#!/usr/bin/env python3
"""CLIENTS study: when the first buy after a dump lands in the NEXT slot (no reacting buy in the dump's slot), where in the next
block does it land? (MEASURED, market-wide). Early index = it was waiting for the next block (backlog); late = slow arrival."""
import json, sys, collections
M = json.load(open(sys.argv[1]))
def cls(c):
    if c == "HarmonicAgave": return "harmonic"
    if c in ("HarmonicFiredancer", "HarmonicFrankendancer"): return "harmonicFD"
    return {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "firebam", "Firedancer": "fd", "Frankendancer": "fd", "Rakurai": "rakurai", "Agave": "agave"}.get(c, "other")
agg = collections.defaultdict(list)
for d in M["dumps"]:
    s, di, n, sol, reacts, nf, navail, c, tp = d
    if reacts or not nf or not navail: continue
    if di / n > 0.75: continue      # dump in the first 75% of its block: the slot had time left
    agg[(cls(c), min(tp, 3))].append(nf[1])
print("first buy in the NEXT slot (dump in first 75% of its block, no reacting buy in its slot): next-slot index p25/p50/p75, n")
for k in ["bam", "firebam", "harmonic", "harmonicFD", "jito", "agave", "fd", "rakurai"]:
    row = []
    for tp in range(4):
        v = sorted(agg.get((k, tp), []))
        if len(v) >= 15: row.append(f"T{tp+1}->T{tp+2 if tp<3 else 'next'}: {v[len(v)//4]}/{v[len(v)//2]}/{v[3*len(v)//4]} (n={len(v)})")
    print(f"{k:11s} " + " | ".join(row))
