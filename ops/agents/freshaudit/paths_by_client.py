#!/usr/bin/env python3
# r2 (leader schedule known): for OK follower buys after >=1 SOL dumps in the SAME slot, which paid-tip path (relay) shows up
# early (dIdx<40) vs late, per leader client; excludes known limit-spam wallets (fail rate > 80%)
import json, gzip, collections, statistics as st
A = "/home/moiz/sniper/ops/agents/freshaudit"
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))
LS = LB["leaders"]; NODES = LB["nodes"]
FOL = json.load(open(f"{A}/out/followers_r2.json"))
spam = {w[:10] for w, v in FOL.items() if v["n"] >= 50 and v["fail"] / v["n"] > 0.8}
def client(slot):
    l = LS.get(str(slot)); return (NODES.get(l, {}).get("class") or "?") if l else "?"
C = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, []]))
tot = collections.Counter()
for l in gzip.open(f"{A}/out/comp_r2.jsonl.gz", "rt"):
    d = json.loads(l)
    if d["sol"] < 1.0 or not (25e9 <= d["vsol"] <= 110e9): continue
    cl = client(d["s"]); tot[cl] += 1
    for f in d["fol"]:
        ds, i, sg, err, isbuy, sol, pr, rel, tip, cup, cul, fee, progs, user, sig = f
        if ds != 0 or not isbuy or err or (sg and sg[:10] in spam): continue
        di = i - d["i"]
        x = C[cl][rel]; x[0] += 1; x[1] += di < 40; x[2].append(di)
print("dumps by leader class:", dict(tot))
for cl, R in C.items():
    tot_ok = sum(v[0] for v in R.values()); tot_early = sum(v[1] for v in R.values())
    print(f"\n== leader class {cl}: same-slot ok follower buys {tot_ok}, early (dIdx<40) {tot_early} ({tot_early/max(1,tot_ok):.0%})")
    print(f"   {'path(tip paid)':<26} {'n':>6} {'early%':>7} {'dIdx med':>8} {'share of early':>14}")
    for rel, v in sorted(R.items(), key=lambda kv: -kv[1][0])[:14]:
        print(f"   {rel:<26} {v[0]:>6} {v[1]/v[0]:>7.0%} {st.median(v[2]):>8.0f} {v[1]/max(1,tot_early):>14.0%}")
