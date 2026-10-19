#!/usr/bin/env python3
"""Receive-path stages of the udp-shreds feed from R lines of a feed_race log.
Stages (us): A kernel(completing pkt) -> recvmmsg returned; B batch return -> this packet's handling start (queue inside
the batch); C handling start -> tx out of the assembler (parse + assemble + decode); total kernel -> decoded. Also
D: kernel time of the completing shred - kernel time of the slot's ... (not here). Usage: rpath.py LOG [feed]"""
import sys
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
feed = sys.argv[2] if len(sys.argv) > 2 else "constantk"
split = int(sys.argv[3]) if len(sys.argv) > 3 else None   # ns timestamp: report before / after separately
rows = {"create": [], "tx": []}
if split: rows = {"create (before)": [], "tx (before)": [], "create (after)": [], "tx (after)": []}
for line in open(sys.argv[1], errors="replace"):
    if not line.startswith("R\t"): continue
    p = line.rstrip("\n").split("\t")
    if p[1] != feed: continue
    tk, cr, tp, tb, ts, td = int(p[2]), p[5] == "1", int(p[6]), int(p[7]), int(p[8]), int(p[9])
    k = "create" if cr else "tx"
    if split: k += " (after)" if tp >= split else " (before)"
    rows[k].append((tb - tp, ts - tb, td - ts, td - tp, tp - tk))
for k, v in rows.items():
    if not v: continue
    print(f"-- {k}s n={len(v)}  (us)       p50      p90      p99      max")
    for i, name in enumerate(["A kernel->recvmmsg ret", "B batch queue", "C assemble+decode", "TOTAL kernel->decoded", "pkt == completing shred? (0)"]):
        col = [x[i] / 1000 for x in v]
        print(f"   {name:24s} {pct(col,.5):8.1f} {pct(col,.9):8.1f} {pct(col,.99):8.1f} {max(col):8.1f}")
