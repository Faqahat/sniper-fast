#!/usr/bin/env python3
"""PoH-vs-arrival analysis on an entries feed (erpc) from a feed_race log.
For each slot followed from its start with 64 consistent ticks: position of each entry on the leader's PoH clock
(hashes / hashes-per-tick, in ticks), wall length of a tick from the arrival slope, the slot's arrival constant
c_S = min(t_rx - pos*T) (when the slot 'started' as seen through the feed, incl. the feed delay L), the excess delay
of each entry over that envelope (batching / shred assembly), continuity within a leader's 4 slots, and the handover
gap between leaders. Also the other feeds' first-shred time relative to c_S.
Usage: poh_an.py LOG [feed=erpc] [leaders.json]"""
import sys, json, collections, statistics as st

def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
def fmt(v): return f"n={len(v)} p10 {pct(v,.1):.2f} p50 {pct(v,.5):.2f} p90 {pct(v,.9):.2f}" if v else "n=0"

log = sys.argv[1]; FEED = sys.argv[2] if len(sys.argv) > 2 else "erpc"
L = json.load(open(sys.argv[3] if len(sys.argv) > 3 else "/root/gap/leaders.json"))
def node(slot):
    i = L["leaders"].get(str(slot)); return i, (L["nodes"].get(i, {}) if i else {})

ents = collections.defaultdict(list)      # slot -> [(t, eidx, cum, ntx, ticks_before)]
creates = collections.defaultdict(set)    # slot -> eidx of creates
first = collections.defaultdict(dict)     # slot -> feed -> first shred/msg time (S lines; U status 3 for yellowstone)
for line in open(log, errors="replace"):
    p = line.rstrip("\n").split("\t")
    if p[0] == "E" and p[1] == FEED:
        ents[int(p[3])].append((int(p[2]), int(p[4]), int(p[5]), int(p[6]), int(p[7])))
    elif p[0] == "X" and p[1] == FEED and p[5] == "1" and p[6] != "-":
        creates[int(p[3])].add(int(p[6]))
    elif p[0] == "S":
        first[int(p[3])].setdefault(p[1], int(p[2]))
    elif p[0] == "U" and p[4] == "3":
        first[int(p[3])].setdefault(p[1] + "@fs", int(p[2]))
slots = sorted(ents)[1:]   # the first slot was joined midway
good = {}
bad = collections.Counter()
for s in slots:
    e = sorted(ents[s], key=lambda x: x[1])
    if not e or e[0][1] != 0 or any(e[i][1] != i for i in range(len(e))): bad["gap/order"] += 1; continue
    ticks = [x for x in e if x[3] == 0]
    if len(ticks) != 64: bad[f"ticks!=64"] += 1; continue
    cums = [x[2] for x in ticks]
    diffs = [b - a for a, b in zip([0] + cums[:-1], cums)]
    hpt = st.median(diffs)
    if hpt <= 0 or any(abs(d - hpt) > 0.01 * hpt for d in diffs): bad["hpt irregular"] += 1; continue
    good[s] = (e, hpt)
print(f"slots: {len(slots)} followed, {len(good)} usable, rejected {dict(bad)}")

# wall length of one tick: per slot, slope of arrival vs PoH position between the first and last tick arrivals
Tt = []
for s, (e, hpt) in good.items():
    tk = [x for x in e if x[3] == 0]
    a, b = tk[0], tk[-1]
    pa, pb = a[2] / hpt, b[2] / hpt
    if pb - pa > 30: Tt.append((b[0] - a[0]) / 1e6 / (pb - pa))
T = st.median(Tt)
print(f"tick length from arrivals: {fmt(Tt)} ms -> T = {T:.4f} ms, slot = {64*T:.1f} ms")

C = {}; exc_all = []; exc_tx = []; exc_cr = []; exc_first = []
for s, (e, hpt) in good.items():
    v = [(x[0] / 1e6 - (x[2] / hpt) * T, x) for x in e]
    c = min(a for a, _ in v); C[s] = c
    for a, x in v:
        exc_all.append(a - c)
        if x[3] > 0: exc_tx.append(a - c)
        if x[1] in creates.get(s, ()): exc_cr.append(a - c)
    exc_first.append(v[0][0] - c)
print("\n-- excess delay over the slot's best (arrival - PoH) envelope, ms (batching + shred assembly + feed jitter)")
print("  all entries   ", fmt(exc_all)); print("  tx entries    ", fmt(exc_tx)); print("  create entries", fmt(exc_cr))
print("  slot's 1st msg", fmt(exc_first))
# where in the slot the envelope minimum sits (early/late)
# continuity and handover
same = []; hand = collections.defaultdict(list); hand_all = []
def bucket(r):
    if r is None: return "?"
    return "<3" if r < 3 else ("3-20" if r < 20 else ("20-100" if r < 100 else ">100"))
for s in sorted(C):
    if s - 1 not in C: continue
    d = C[s] - (C[s - 1] + 64 * T)
    ia, na = node(s - 1); ib, nb = node(s)
    if ia == ib: same.append(d)
    else:
        hand_all.append(d)
        hand[(bucket(na.get("rtt_ms")), bucket(nb.get("rtt_ms")))].append(d)
print("\n-- c_S continuity, same leader (should be ~0):", fmt(same))
print("-- handover gap c_S - (c_{S-1} + slot) between leaders, ms = R(A->B) + replay + L_B - L_A:", fmt(hand_all))
print("   by (rtt to prev leader A, rtt to new leader B) [ms buckets]:")
for k in sorted(hand, key=lambda k: -len(hand[k])):
    print(f"   A {k[0]:>6s}  B {k[1]:>6s}  {fmt(hand[k])}")
# other feeds' first shred relative to the slot envelope c_S (c_S = leader slot start + L_erpc_min)
print("\n-- each feed's first data of the slot minus erpc envelope c_S (ms; negative = before the envelope):")
fs = collections.defaultdict(list)
for s, c in C.items():
    for f, t in first.get(s, {}).items(): fs[f].append(t / 1e6 - c)
for f in sorted(fs): print(f"   {f:20s} {fmt(fs[f])}")
# by leader rtt: the slot envelope relative to... (only relative): first erpc msg excess by leader bucket
byb = collections.defaultdict(list)
for s, (e, hpt) in good.items():
    byb[bucket(node(s)[1].get("rtt_ms"))].append(e[0][0] / 1e6 - C[s])
print("\n-- first-message excess by leader RTT bucket:")
for k in sorted(byb): print(f"   {k:>6s} {fmt(byb[k])}")
