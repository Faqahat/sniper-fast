#!/usr/bin/env python3
"""PoH cross-check with leader-published shreds: for creates in slots the leader publishes to DZ, the create's PoH
offset p_c (erpc entries: hashes / hashes-per-tick x tick, tick = SLOT_MS/64) vs its arrival at each feed relative to
dz-leader's FIRST shred of the slot. If the leader emitted shreds in real time, (t_c - t_first) - p_c would be ~0;
its median is the create's extra wait at the leader (broadcast batching) beyond the slot's first shred.
Usage: poh_dz.py LOG [SLOT_MS=203.5]"""
import sys, collections
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
log = sys.argv[1]; SLOT_MS = float(sys.argv[2]) if len(sys.argv) > 2 else 203.5; TICK = SLOT_MS / 64
ent = collections.defaultdict(dict); ticks = collections.defaultdict(list); first = collections.defaultdict(dict)
cr = {}; arr = collections.defaultdict(dict)
for line in open(log, errors="replace"):
    p = line.rstrip("\n").split("\t")
    if p[0] == "E" and p[1] == "erpc":
        s = int(p[3]); e = int(p[4]); cum = int(p[5]); ntx = int(p[6])
        ent[s][e] = cum
        if ntx == 0: ticks[s].append(cum)
    elif p[0] == "S": first[int(p[3])].setdefault(p[1], int(p[2]))
    elif p[0] == "X":
        if p[5] == "1":
            if p[1] == "erpc" and p[6] != "-": cr[p[4]] = (int(p[3]), int(p[6]))
            arr[p[4]].setdefault(p[1], int(p[2]))
res = collections.defaultdict(list); pcs = []
for sig, (s, e) in cr.items():
    tk = sorted(ticks.get(s, []))
    if len(tk) != 64 or "dz-leader" not in first.get(s, {}) or e not in ent[s]: continue
    hpt = (tk[-1]) / 64
    pc = ent[s][e] / hpt * TICK
    pcs.append(pc)
    t0 = first[s]["dz-leader"]
    for f, t in arr[sig].items():
        res[f].append((t - t0) / 1e6 - pc)
print(f"creates with PoH and a dz-leader slot: {len(pcs)}; create PoH offset in slot p50 {pct(pcs,.5):.1f} ms")
print("(arrival - dz-leader first shred of the slot) - create PoH offset, ms  [the create's wait beyond real time]")
for f in sorted(res): v = res[f]; print(f"  {f:14s} n={len(v):4d} p10 {pct(v,.1):7.2f} p50 {pct(v,.5):7.2f} p90 {pct(v,.9):7.2f}")
