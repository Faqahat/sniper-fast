#!/usr/bin/env python3
# haqq SEND PATHS, part 2 (local): speed of its dip buys by landed path and leader client. Delay = block-position ms proxy from the
# >= 1 SOL dump to its buy (same metric for our fills); same-slot share; buyers ahead of it; 6042 failures in the dump's slot window.
import sys, json, collections, numpy as np, pickle, zlib, glob
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_load
P1 = {(r["s"], r["i"]): r for r in json.load(open(f"{H.OUT}/paths1.json"))}
eps = h_load.load(with_ticks=False)
rows = []
for e in eps:
    for n, b in enumerate(e["buys"]):
        p = P1.get((b["s"], b["i"]))
        if not p or not b["dip"]: continue
        rows.append(dict(svc=p["svc"], client=p["client"], rtt=p["rtt"], delay=b["delay"], same=b["trig_ds"] == 0, ds=b["trig_ds"], size=b["sol"], pos=p["pos"], tip=p["tip"], cup=p["cup"], run=e["run"]))
def q(v, ps=(25, 50, 75)): return " / ".join(f"{x:.0f}" for x in np.percentile(v, ps)) if len(v) else "-"
print(f"dip buys with path: {len(rows)}")
print("\nby landed path: n | delay ms p25/50/75 | same slot as dump | block pos median")
for sv, n in collections.Counter(r["svc"] for r in rows).most_common(8):
    s = [r for r in rows if r["svc"] == sv]
    print(f"   {sv:10s} {n:5d} | {q([r['delay'] for r in s])} | {np.mean([r['same'] for r in s]):.0%} | {np.median([r['pos'] for r in s if r['pos'] is not None]):.2f}")
print("\nby leader client: n | delay p25/50/75 | same slot | top paths")
for cl in ("bam", "jito", "harmonic", "fd", "agave", "other"):
    s = [r for r in rows if r["client"] == cl]
    if s: print(f"   {cl:9s} {len(s):5d} | {q([r['delay'] for r in s])} | {np.mean([r['same'] for r in s]):.0%} | {collections.Counter(r['svc'] for r in s).most_common(4)}")
print("\nclient x path (n >= 40): delay median, same slot")
for cl in ("bam", "jito", "harmonic", "fd", "agave"):
    for sv in ("helius", "none", "0slot", "astralane", "nozomi", "jito"):
        s = [r for r in rows if r["client"] == cl and r["svc"] == sv]
        if len(s) >= 40: print(f"   {cl:9s} {sv:10s} n {len(s):5d} delay median {np.median([r['delay'] for r in s]):5.0f} ms, same slot {np.mean([r['same'] for r in s]):.0%}")
print("\nby leader distance (RTT from Frankfurt ms): n | delay p25/50/75 | same slot")
for lab, lo, hi in (("<5", 0, 5), ("5-20", 5, 20), ("20-60", 20, 60), ("60-120", 60, 120), (">=120", 120, 1e9)):
    s = [r for r in rows if r["rtt"] is not None and lo <= r["rtt"] < hi]
    if s: print(f"   {lab:7s} {len(s):5d} | {q([r['delay'] for r in s])} | {np.mean([r['same'] for r in s]):.0%} | {collections.Counter(r['svc'] for r in s).most_common(3)}")
json.dump(rows, open(f"{H.OUT}/paths2_rows.json", "w"))
