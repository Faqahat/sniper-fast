#!/usr/bin/env python3
"""For each landed copy of a run: the slot's leader, whether its advertised TPU-QUIC is on its gossip host (same IP)
or elsewhere (a relayer in front), and our ms after the trigger. usage: leaders6.py <run>"""
import json, types, sys
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/"')[0], _ns)
T = types.SimpleNamespace(**_ns)
B = f"/root/arb-lab/runs/{sys.argv[1]}/"
log = {}
for line in open(B + "poh.log"):
    s8, slot, ms = line.split(); log.setdefault(s8, (int(slot), float(ms)))
at = lambda sig: log.get(T.b58d(sig)[:8].hex()) if sig else None
a = {x["attempt"]: x for x in map(json.loads, open(B + "attempts.jsonl"))}
o = [x for x in map(json.loads, open(B + "outcomes.jsonl")) if x.get("landed")]
nodes = {n["pubkey"]: n for n in T.rpc("getClusterNodes", [])}
slots = sorted(x["slot"] for x in o)
lead = dict(zip(range(slots[0], slots[-1] + 1), T.rpc("getSlotLeaders", [slots[0], slots[-1] - slots[0] + 1])))
for x in o:
    tp, op = at(a[x["attempt"]]["trigger"]), at(x["sig"])
    ms = round((op[0] - tp[0]) * 400 + op[1] - tp[1], 1) if tp and op else None
    k = lead.get(x["slot"]); n = nodes.get(k, {})
    g, q = (n.get("gossip") or "").split(":")[0], (n.get("tpuQuic") or "").split(":")[0]
    print(f"{x['attempt']:>3} {x['landed']:<11} ms {ms!s:>7}  leader {k[:8] if k else None}  tpuQuic {'same host' if g == q else 'OTHER host ' + q}  ver {n.get('version')}")
