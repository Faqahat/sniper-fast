#!/usr/bin/env python3
"""Slot-to-slot first-shred spacing from S lines of a feed (stdin: grep '^S' LOG). Same-leader spacing = slot length
+ jitter; at a leader handover the extra = (B starts after receiving A's last shreds and replaying) + L_B - L_A.
Usage: grep -P '^S\tconstantk' LOG | handover.py [leaders.json]"""
import sys, json, collections
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
def fmt(v): return f"n={len(v):4d} p10 {pct(v,.1):7.2f} p50 {pct(v,.5):7.2f} p90 {pct(v,.9):7.2f}" if v else "n=0"
L = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/root/gap/leaders.json"))
t = {}
for line in sys.stdin:
    p = line.split("\t"); t.setdefault(int(p[3]), int(p[2]) / 1e6)
def nd(s):
    i = L["leaders"].get(str(s)); return i, L["nodes"].get(i, {}) if i else {}
def b(r): return "?" if r is None else ("<3" if r < 3 else ("3-20" if r < 20 else ("20-100" if r < 100 else ">100")))
same = []; hand = collections.defaultdict(list); cityh = collections.defaultdict(list)
for s in sorted(t):
    if s - 1 not in t: continue
    g = t[s] - t[s - 1]
    if g < 0 or g > 1000: continue
    ia, na = nd(s - 1); ib, nb = nd(s)
    if ia == ib: same.append(g)
    else:
        hand[(b(na.get("rtt_ms")), b(nb.get("rtt_ms")))].append(g)
base = pct(same, .5)
print(f"same-leader spacing (slot length): {fmt(same)} ms")
print("handover spacing minus slot length (ms), by (RTT to old leader A, RTT to new leader B):")
for k in sorted(hand, key=lambda k: -len(hand[k])):
    v = [x - base for x in hand[k]]
    print(f"  A {k[0]:>6s} -> B {k[1]:>6s}  {fmt(v)}")
