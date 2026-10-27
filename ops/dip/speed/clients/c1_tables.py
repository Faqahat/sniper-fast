#!/usr/bin/env python3
"""CLIENTS study (10-25, read-only): per-client tables from speed_truth/attempts.csv.
MEASURED tables: by client x turn slot, by client x landed path, block position of our buy vs the dump."""
import csv, collections, statistics as st
A = "/home/moiz/sniper-data/speed_truth/attempts.csv"
rows = list(csv.DictReader(open(A)))
def cls(c):
    if "Harmonic" in c: return "harmonic" if c == "HarmonicAgave" else "harmonicFD"
    return {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "firebam", "Firedancer": "fd", "Rakurai": "rakurai", "Agave": "agave"}.get(c, c)
f = lambda x: float(x) if x not in ("", None) else None
def med(v):
    v = [x for x in v if x is not None]
    return round(st.median(v), 1) if v else None
def q(v, p):
    v = sorted(x for x in v if x is not None)
    if not v: return None
    return round(v[min(len(v) - 1, int(p * len(v)))], 1)
for r in rows:
    r["k"] = cls(r["client"]); r["fill"] = r["result"] == "FILL"; r["same"] = r["slot_delta"] == "0"
    r["path"] = r["landed_path"] if not r["landed_path"].startswith("multi") else "multi-tip(pre-nonce)"
print("== 1. by client: n, fill%, same-slot%, land_feed p25/p50/p75, send->seen p50 (same-slot only), our idx - dump idx p50 (same slot)")
by = collections.defaultdict(list)
for r in rows: by[r["k"]].append(r)
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    ss = [r for r in v if r["same"]]
    print(f"{k:11s} n={len(v):3d} fill={sum(r['fill'] for r in v)/len(v):4.0%} same={len(ss)/len(v):4.0%} "
          f"land_feed {q([f(r['land_feed_ms']) for r in v],.25)}/{med([f(r['land_feed_ms']) for r in v])}/{q([f(r['land_feed_ms']) for r in v],.75)} "
          f"| same-slot: land_feed {med([f(r['land_feed_ms']) for r in ss])} send->seen {med([f(r['send_to_seen_ms']) for r in ss])} "
          f"idx gap {med([int(r['our_idx'])-int(r['dump_idx']) for r in ss])} dump pos {med([int(r['dump_idx'])/max(1,int(r['dump_block_n'])) for r in v])} "
          f"| first reacting rival B400 {med([f(r['first_reacting_rival_B400_ms']) for r in v])}")
print("\n== 2. spill rate by client x turn slot (1 = first slot of the leader's turn)")
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    t = collections.defaultdict(lambda: [0, 0])
    for r in v:
        t[r["turn_slot"]][0] += 1; t[r["turn_slot"]][1] += (not r["same"])
    print(f"{k:11s} " + "  ".join(f"slot{s}: {t[s][1]}/{t[s][0]}" for s in sorted(t)))
print("\n== 3. by client x landed path: n, fills, same-slot, land_feed p50")
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    t = collections.defaultdict(list)
    for r in v: t[r["path"]].append(r)
    print(f"{k:11s} " + " | ".join(f"{p}: {len(w)} land, {sum(r['fill'] for r in w)} fill, {sum(r['same'] for r in w)} same, {med([f(r['land_feed_ms']) for r in w])} ms" for p, w in sorted(t.items(), key=lambda kv: -len(kv[1]))))
print("\n== 4. spill vs time left in the dump's block (B400-style: (1 - idx/max(n,idx+1)) x 212 ms), by client")
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    b = collections.defaultdict(lambda: [0, 0])
    for r in v:
        left = (1 - int(r["dump_idx"]) / max(int(r["dump_block_n"]), int(r["dump_idx"]) + 1)) * 212
        key = "<40" if left < 40 else ("40-80" if left < 80 else ">=80")
        b[key][0] += 1; b[key][1] += (not r["same"])
    print(f"{k:11s} " + "  ".join(f"{s}: {b[s][1]}/{b[s][0]} spill" for s in ("<40", "40-80", ">=80")))
