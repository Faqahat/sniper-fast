#!/usr/bin/env python3
"""CLIENTS study: is the leader's advertised TPU its own IP (direct) or another host (relayer / BAM node / remote TPU)?
From the leader books (gossip snapshot: ips = unique IPs of tpuQuic, tpu, gossip, tpuForwardsQuic, in that order).
Joins with attempts.csv: our landing by client x TPU-front class. MEASURED (gossip snapshot of 10-23/24; may have changed)."""
import json, csv, collections, statistics as st
books = ["/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json", "/home/moiz/sniper/ops/region/leader_rtt_ams.json"]
L = {}
for b in books:
    for pk, r in json.load(open(b))["leaders"].items():
        L.setdefault(pk, r)
def front(r):
    ips = r.get("ips") or []
    tpu = (r.get("tpu") or "").rsplit(":", 1)[0].strip("[]")
    if not tpu or len(ips) < 2: return "direct" if tpu else "?"
    # gossip ip = the one that is not the tpu ip (ips order: tpuQuic, tpu, gossip, fwd)
    return "fronted" if tpu != ips[-1] or len(set(ips)) > 1 else "direct"
cnt = collections.Counter((r.get("client"), front(r)) for r in L.values())
print("== leaders by client x TPU front (fronted = advertised TPU IP differs from another of its IPs)")
for (c, f), n in sorted(cnt.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])): print(f"  {c:20s} {f:8s} {n}")
print("\n== our attempts by client x front: n, fill, same-slot, land_feed p50, send->seen p50 (same slot)")
rows = list(csv.DictReader(open("/home/moiz/sniper-data/speed_truth/attempts.csv")))
g = collections.defaultdict(list)
for r in rows:
    l = L.get(r["leader"]); g[(r["client"], front(l) if l else "?")].append(r)
med = lambda v: round(st.median(v), 1) if v else None
for (c, f), v in sorted(g.items()):
    ss = [r for r in v if r["slot_delta"] == "0"]
    print(f"  {c:20s} {f:8s} n={len(v):3d} fill={sum(r['result']=='FILL' for r in v):3d} same={len(ss):3d} land_feed={med([float(r['land_feed_ms']) for r in v])} "
          f"seen(same)={med([float(r['send_to_seen_ms']) for r in ss if r['send_to_seen_ms']])} spill_turn1={sum(1 for r in v if r['turn_slot']=='1' and r['slot_delta']!='0')}/{sum(1 for r in v if r['turn_slot']=='1')}")
