#!/usr/bin/env python3
"""CLIENTS study: reacting buys on Jito leaders by TPU front (relayer vs own TPU) x tip path (MEASURED, market-wide).
If plain/no-tip txs are held by the relayer (packet_delay_ms), they should land later on relayer-fronted leaders."""
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
    if port == "11228": return "relayer"
    if len(r.get("ips") or []) > 1: return "relayer"
    return "own-tpu"
want = sys.argv[2] if len(sys.argv) > 2 else "JitoLabs"
rows = collections.defaultdict(list); first = collections.defaultdict(collections.Counter); nd = collections.Counter()
for d in M["dumps"]:
    s, di, n, sol, reacts, nf, navail, c, tp = d
    if c != want or not reacts: continue
    k = kind(tl.leader(s))
    nd[k] += 1; first[k][reacts[0][2]] += 1
    for r in reacts:
        rows[(k, r[2])].append((r[1] - di) / max(400, n) * 212.0)
for k in ("own-tpu", "relayer"):
    print(f"-- {want} {k}: dumps with a reaction {nd[k]}")
    tot = sum(len(v) for (kk, p), v in rows.items() if kk == k)
    for (kk, p), v in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        if kk != k or len(v) < 40: continue
        vs = sorted(v)
        print(f"   {p:13s} n={len(v):5d} B-ms p25/p50 {vs[len(vs)//4]:5.1f}/{vs[len(vs)//2]:5.1f}  first {first[k][p]:4d} lift {(first[k][p]/nd[k])/(len(v)/tot):4.2f}")
