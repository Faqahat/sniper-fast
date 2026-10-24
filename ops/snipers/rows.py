#!/usr/bin/env python3
# READ-ONLY, offline: outside create-slot buyers from bundlestudy outputs (dev, glued creator bundle and creator-linked Jito
# bundles already excluded there), with fee = priority + tips (+ the bundle's tip when the buy sits in its own Jito bundle and
# the tx itself carries no tip) and the "cheap early" flag (lands ahead of later buyers while paying < 25% of their median fee).
# usage: python3 -I rows.py <out rows.json> <bundlestudy json> [...] [--exclude hist.json]
import sys, json, statistics, collections
args = sys.argv[1:]; ex = set()
if "--exclude" in args:
    i = args.index("--exclude"); ex = set(json.load(open(args[i + 1]))); args = args[:i] + args[i + 2:]
OUT, INS = args[0], args[1:]
rows = []
for f in INS:
    for x in json.load(open(f)):
        if not x: continue
        sn = [r for r in x["rows"] if r["cls"] == "sniper" and r["buy"] and r["ok"]]
        for i, r in enumerate(sn):
            tips = sum(t[1] for t in r["tips"])
            btip = (r["bundle"] or {}).get("tip") if isinstance(r["bundle"], dict) else None
            fee = r["prio"] + tips + (btip if (btip and not r["tips"]) else 0)
            rows.append(dict(mint=x["mint"], S=x["S"], pos=r["pos"], k=i + 1, sol=r["sol"], prio=r["prio"], tips=tips, fee=fee,
                             ratio=fee / r["sol"] if r["sol"] else 0, w=r["users"][0], payer=r["payer"], bundle="Y" if r["bundle"] else "", sig=r["sig"]))
by = collections.defaultdict(list)
for r in rows: by[r["mint"]].append(r)
for m, rs in by.items():
    rs.sort(key=lambda r: r["pos"])
    for i, r in enumerate(rs):
        later = [x["fee"] for x in rs[i + 1:i + 4]]
        r["cheap_early"] = bool(later) and r["fee"] < 0.25 * statistics.median(later) and r["ratio"] < 0.005
keep = [r for r in rows if r["w"] not in ex]
json.dump(keep, open(OUT, "w"))
w = {r["w"] for r in keep if not r["cheap_early"] and r["sol"] >= 0.15}
print(f"{len(rows)} outside create-slot buys in {len(by)} launches; {len(keep)} by wallets not analyzed yet; new candidate wallets (>=0.15 SOL, not cheap-early): {len(w)}")
