#!/usr/bin/env python3
"""CLIENTS study: JitoLabs leaders split by TPU type from gossip (leader books 10-23/24):
  relayer = advertised TPU on port 11228 (jito-relayer default) or on another host's IP; own = validator's own TPU port.
Our attempts on each (MEASURED). Code: jito-relayer forwarder delays packets packet_delay_ms (default 50) before the validator;
jito-solana drops packets on its own TPU while the relayer TPU is advertised (fetch_stage_manager.rs should_forward_packets)."""
import json, csv, collections, statistics as st
L = {}
for b in ["/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json", "/home/moiz/sniper/ops/region/leader_rtt_ams.json"]:
    for pk, r in json.load(open(b))["leaders"].items(): L.setdefault(pk, r)
def kind(pk):
    r = L.get(pk)
    if not r or not r.get("tpu"): return "?"
    ip, port = r["tpu"].rsplit(":", 1)
    if port == "11228": return "relayer(colo)"
    if len(r.get("ips") or []) > 1: return "relayer(remote)"
    return "own-tpu"
rows = [r for r in csv.DictReader(open("/home/moiz/sniper-data/speed_truth/attempts.csv")) if r["client"] in ("JitoLabs", "Rakurai")]
g = collections.defaultdict(list)
for r in rows: g[(r["client"], kind(r["leader"]))].append(r)
med = lambda v: round(st.median(v), 1) if v else None
for (c, k), v in sorted(g.items()):
    ss = [r for r in v if r["slot_delta"] == "0"]
    paths = collections.Counter(r["landed_path"] for r in v)
    print(f"{c:9s} {k:16s} n={len(v):3d} fills={sum(r['result']=='FILL' for r in v):3d} same={len(ss):3d} ({len(ss)/len(v):.0%}) land_feed p50={med([float(r['land_feed_ms']) for r in v])} "
          f"same-slot land_feed={med([float(r['land_feed_ms']) for r in ss])} seen={med([float(r['send_to_seen_ms']) for r in ss if r['send_to_seen_ms']])} "
          f"turn1 spill={sum(1 for r in v if r['turn_slot']=='1' and r['slot_delta']!='0')}/{sum(1 for r in v if r['turn_slot']=='1')} "
          f"rival1 B400={med([float(r['first_reacting_rival_B400_ms']) for r in v if r['first_reacting_rival_B400_ms']])} paths={dict(paths)}")
