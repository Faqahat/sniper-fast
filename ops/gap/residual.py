#!/usr/bin/env python3
"""Leader broadcast batching: per slot, the first-shred time of each FEC set; the expected wait of a tx recorded at a
random moment until its set is broadcast ~ sum(g^2)/(2 sum g) over the gaps g between consecutive sets (time-weighted).
Also: the slot's first shred vs its second set, and gaps by leader client. Usage: residual.py PCAP [leaders.json]"""
import struct, sys, collections, json
L = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "/root/gap/leaders.json"))
f = open(sys.argv[1], "rb"); gh = f.read(24); nano = struct.unpack("<I", gh[:4])[0] == 0xa1b23c4d
link = struct.unpack("<I", gh[20:24])[0]; OFF = {1: 14, 113: 16, 276: 20, 101: 0, 12: 0}.get(link, 14)
first = {}
while True:
    h = f.read(16)
    if len(h) < 16: break
    ts, tf, caplen, _ = struct.unpack("<IIII", h); pkt = f.read(caplen)
    t = ts * 10**9 + (tf if nano else tf * 1000)
    ihl = (pkt[OFF] & 0x0f) * 4; p = pkt[OFF + ihl + 8:]
    if len(p) < 83: continue
    slot = struct.unpack("<Q", p[65:73])[0]; fec = struct.unpack("<I", p[79:83])[0]
    k = (slot, fec)
    if k not in first: first[k] = t
per = collections.defaultdict(list)
for (s, fec), t in first.items(): per[s].append(t)
def cls(s):
    i = L["leaders"].get(str(s)); return L["nodes"].get(i, {}).get("class", "unknown") if i else "unknown"
agg = collections.defaultdict(lambda: [0.0, 0.0, 0])
for s, v in per.items():
    v.sort()
    if len(v) < 5: continue
    for a, b in zip(v, v[1:]):
        g = (b - a) / 1e6
        for k in ("all", cls(s)):
            agg[k][0] += g * g; agg[k][1] += g; agg[k][2] += 1
for k, (s2, s1, n) in sorted(agg.items(), key=lambda x: -x[1][2]):
    print(f"{k:10s} gaps={n:6d} mean gap {s1/n:6.2f} ms  time-weighted residual wait to broadcast {s2/(2*s1):6.2f} ms")
