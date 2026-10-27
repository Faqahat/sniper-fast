#!/usr/bin/env python3
"""CLIENTS study: block size proxy by slot-in-window for Jito leaders split by TPU front, and for other clients (MEASURED)."""
import json, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/truth")
import tl
M = json.load(open(sys.argv[1]))
L = {}
for bk in ["/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json", "/home/moiz/sniper/ops/region/leader_rtt_ams.json"]:
    for pk, r in json.load(open(bk))["leaders"].items(): L.setdefault(pk, r)
def kind(pk):
    r = L.get(pk)
    if not r or not r.get("tpu"): return "?"
    ip, port = r["tpu"].rsplit(":", 1)
    if port == "11228" or len(r.get("ips") or []) > 1: return "relayer"
    return "own-tpu"
agg = collections.defaultdict(list)
for b in M["blocks"]:
    s, n, npump, nf, desc, asc, c, tp = b
    if c != "JitoLabs" or tp is None: continue
    agg[(kind(tl.leader(s)), s % 4)].append(n)
for k in ("own-tpu", "relayer"):
    print(k, "  ".join(f"T{t+1}: p50 {sorted(agg[(k,t)])[len(agg[(k,t)])//2]} (n={len(agg[(k,t)])})" for t in range(4) if agg[(k, t)]))
