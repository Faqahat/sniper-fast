#!/usr/bin/env python3
"""Creates (and pump txs) a UDP feed missed vs Kaldera; for slots inside a pcap window, whether that slot had FEC sets
with missing data shreds (recoverable from code shreds) — i.e. our assembler (no Reed-Solomon recovery) stalled.
Usage: misses.py LOG PCAP [udpfeed=constantk] [ref=kaldera]"""
import sys, struct, collections
log, pcap = sys.argv[1], sys.argv[2]
U = sys.argv[3] if len(sys.argv) > 3 else "constantk"; R = sys.argv[4] if len(sys.argv) > 4 else "kaldera"
seen = collections.defaultdict(dict); slot_of = {}; cr = set(); udp_slots = collections.Counter()
for line in open(log, errors="replace"):
    if not line.startswith("X\t"): continue
    p = line.split("\t")
    if p[1] not in (U, R): continue
    seen[p[4]].setdefault(p[1], int(p[2])); slot_of[p[4]] = int(p[3])
    if p[5] == "1": cr.add(p[4])
    if p[1] == U: udp_slots[int(p[3])] += 1
t_first_u = min(v[U] for v in seen.values() if U in v)
miss_cr = [s for s in cr if R in seen[s] and U not in seen[s] and seen[s][R] > t_first_u + 5e9]
miss_tx = [s for s in seen if R in seen[s] and U not in seen[s] and seen[s][R] > t_first_u + 5e9]
# pcap: per slot, sets with missing data shreds; per slot, max data index seen
f = open(pcap, "rb"); gh = f.read(24); nano = struct.unpack("<I", gh[:4])[0] == 0xa1b23c4d
sets = collections.defaultdict(lambda: [set(), 0]); tmin = tmax = None
while True:
    h = f.read(16)
    if len(h) < 16: break
    ts, tf, caplen, _ = struct.unpack("<IIII", h); pkt = f.read(caplen)
    t = ts * 10**9 + (tf if nano else tf * 1000); tmin = tmin or t; tmax = t
    ihl = (pkt[14] & 0x0f) * 4; p = pkt[14 + ihl + 8:]
    if len(p) < 85: continue
    v = p[64]; hi = v & 0xf0
    slot, idx = struct.unpack("<QI", p[65:77]); fec = struct.unpack("<I", p[79:83])[0]
    if v == 0xa5 or hi in (0x80, 0x90, 0xb0): sets[(slot, fec)][0].add(idx)
    else: sets[(slot, fec)][1] += 1
bad_slots = collections.Counter()
for (slot, fec), (d, c) in sets.items():
    if len([i for i in range(fec, fec + 32) if i in d]) < 32 and (len(d) + c) >= 32: bad_slots[slot] += 1
pslots = {s for s, _ in sets}
inwin = lambda s: seen[s][R] >= tmin and seen[s][R] <= tmax
mc = [s for s in miss_cr if inwin(s)]; mt = [s for s in miss_tx if inwin(s)]
print(f"{U} missed vs {R}: creates {len(miss_cr)} of {sum(1 for s in cr if R in seen[s] and seen[s][R] > t_first_u + 5e9)}, pump txs {len(miss_tx)}")
print(f"inside the pcap window: creates missed {len(mc)}, of which in a slot with an incomplete-but-recoverable FEC set: {sum(1 for s in mc if bad_slots[slot_of[s]])}; slot not in pcap at all: {sum(1 for s in mc if slot_of[s] not in pslots)}")
print(f"  pump txs missed {len(mt)}, in slots with a stalled set: {sum(1 for s in mt if bad_slots[slot_of[s]])}")
allsl = [s for s in pslots]
print(f"  pcap slots {len(allsl)}, slots with a stalled set {len(bad_slots)} ({len(bad_slots)*100/len(allsl):.1f}%)")
for s in mc[:15]: print("   missed create", s, "slot", slot_of[s], "stalled sets in slot:", bad_slots[slot_of[s]], "udp txs logged in slot:", udp_slots[slot_of[s]])
