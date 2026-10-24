#!/usr/bin/env python3
# Multi-region kit: give every leader to AT MOST ONE server, so the two bots never race each other for the same dump.
# A leader goes to the server with the lower ICMP RTT, and only if that RTT is < CLOSE_MS (default 5). Inputs: the leader_rtt
# JSON of each server (leader_rtt.py on each: {"leaders": {pk: {"rtt", "slots_cur", "slots_next", "client"}}}).
# Writes near_leaders_<region>.txt per server into OUT_DIR and prints the slot share each one covers (this / next epoch).
# usage: python3 -I split_near.py fra=/path/leader_rtt_fra.json ams=/path/leader_rtt_ams.json [OUT_DIR=.] [CLOSE_MS=5]
import json, os, sys, collections
args = dict(a.split("=", 1) for a in sys.argv[1:])
OUT = args.pop("OUT_DIR", "."); CLOSE = float(args.pop("CLOSE_MS", "5"))
R = {reg: json.load(open(p))["leaders"] for reg, p in args.items()}
pks = set().union(*[set(v) for v in R.values()])
own = collections.defaultdict(list); share = collections.defaultdict(lambda: [0, 0])
tot = [0, 0]
for pk in pks:
    any_r = next(v[pk] for v in R.values() if pk in v)
    tot[0] += any_r.get("slots_cur", 0); tot[1] += any_r.get("slots_next", 0)
    best = min(((v[pk]["rtt"], reg) for reg, v in R.items() if pk in v and v[pk].get("rtt") is not None), default=None)
    if best and best[0] < CLOSE:
        own[best[1]].append(pk); share[best[1]][0] += any_r.get("slots_cur", 0); share[best[1]][1] += any_r.get("slots_next", 0)
for reg in R:
    path = os.path.join(OUT, f"near_leaders_{reg}.txt")
    open(path, "w").write("\n".join(sorted(own[reg])) + "\n")
    print(f"{reg}: {len(own[reg])} leaders, {100 * share[reg][0] / max(1, tot[0]):.1f}% of slots this epoch, {100 * share[reg][1] / max(1, tot[1]):.1f}% next -> {path}")
both = sum(share[r][0] for r in R)
print(f"together: {100 * both / max(1, tot[0]):.1f}% of slots this epoch (each leader on one server only)")
