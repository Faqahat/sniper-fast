#!/usr/bin/env python3
"""Per-FEC-set arrival timing of raw UDP shreds from a pcap (nanosecond, snaplen >= 128).
Shows: burst spread of a set, how long after the set's first shred all data shreds were in vs when ANY num_data shreds
were in (the earliest Reed-Solomon recovery point), sets incomplete-but-recoverable, and the leader's broadcast cadence
(gap between consecutive sets of a slot). Usage: pcap_fec.py FILE.pcap [leaders.json]"""
import struct, sys, collections, json

def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
def fmt(v): return f"n={len(v)} p10 {pct(v,.1):.3f} p50 {pct(v,.5):.3f} p90 {pct(v,.9):.3f} p99 {pct(v,.99):.3f}" if v else "n=0"

f = open(sys.argv[1], "rb")
gh = f.read(24)
magic = struct.unpack("<I", gh[:4])[0]
nano = magic == 0xa1b23c4d
link = struct.unpack("<I", gh[20:24])[0]
off = 14 if link == 1 else 16       # EN10MB or LINUX_SLL
sets = collections.defaultdict(lambda: {"d": {}, "c": [], "nd": None, "t0": None})
slot_first = {}
n = 0
while True:
    h = f.read(16)
    if len(h) < 16: break
    ts, tf, caplen, _ = struct.unpack("<IIII", h)
    pkt = f.read(caplen)
    t = ts * 1_000_000_000 + (tf if nano else tf * 1000)
    ip = off; ihl = (pkt[ip] & 0x0f) * 4
    p = pkt[ip + ihl + 8:]
    if len(p) < 85: continue
    v = p[64]; hi = v & 0xf0
    data = v == 0xa5 or hi in (0x80, 0x90, 0xb0)
    code = v == 0x5a or hi in (0x40, 0x60, 0x70)
    if not (data or code): continue
    slot, idx = struct.unpack("<QI", p[65:77]); fec = struct.unpack("<I", p[79:83])[0]
    n += 1
    s = sets[(slot, fec)]
    if s["t0"] is None: s["t0"] = t
    slot_first.setdefault(slot, t)
    if data:
        s["d"].setdefault(idx, t)
    else:
        s["c"].append(t)
        s["nd"] = struct.unpack("<H", p[83:85])[0]
print(f"packets {n}, FEC sets {len(sets)}, slots {len(slot_first)}")
spread = []; all_data = []; k_any = []; gain = []; recov_only = 0; incomplete = 0; nd_hist = collections.Counter()
per_slot = collections.defaultdict(list)
for (slot, fec), s in sets.items():
    nd = s["nd"]
    if not nd: continue
    nd_hist[nd] += 1
    per_slot[slot].append((fec, s["t0"]))
    ts_all = sorted(list(s["d"].values()) + s["c"])
    spread.append((ts_all[-1] - ts_all[0]) / 1e6)
    t_k = ts_all[nd - 1] if len(ts_all) >= nd else None
    have = all((fec + i) in s["d"] for i in range(nd))
    if have:
        td = max(s["d"][fec + i] for i in range(nd))
        all_data.append((td - s["t0"]) / 1e6)
        if t_k: k_any.append((t_k - s["t0"]) / 1e6); gain.append((td - t_k) / 1e6)
    else:
        incomplete += 1
        if t_k: recov_only += 1
print(f"data shreds per set: {dict(nd_hist.most_common(5))}")
print("set burst spread (first..last shred of the set), ms:", fmt(spread))
print("all DATA shreds in, after the set's first shred, ms:", fmt(all_data))
print("any num_data shreds in (RS recovery possible), ms: ", fmt(k_any))
print("gain from RS recovery (all-data minus k-any), ms:   ", fmt(gain))
print(f"sets with a data shred missing: {incomplete} of {len(sets)}; of those recoverable from code shreds: {recov_only}")
gaps = []
for slot, v in per_slot.items():
    v.sort()
    for a, b in zip(v, v[1:]): gaps.append((b[1] - a[1]) / 1e6)
print("leader broadcast cadence: gap between consecutive FEC sets of a slot (first shreds), ms:", fmt(gaps))
nsets = [len(v) for v in per_slot.values()]
print("FEC sets per slot:", fmt(nsets))
