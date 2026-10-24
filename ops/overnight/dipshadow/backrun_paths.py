#!/usr/bin/env python3
# How do the dip backrunners send? For every buy in the same slot within 150 ms (block-position proxy) after a dip trigger:
# the landing service it tipped (collector tip accounts -> tipmap), tip size, priority fee, and whether it called pump directly.
# Split by speed bucket and for the fastest wallets (HkQ7hMjy first). Local data only.
# usage: python3 -I backrun_paths.py trig_sigs_all.jsonl backrun_rows.jsonl
import sys, json, collections, statistics
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
ROW = {}
for l in open(sys.argv[2]):
    r = json.loads(l); ROW[r["sig"]] = r
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
       "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", PUMP}
B = []
for l in open(sys.argv[1]):
    e = json.loads(l)
    for x in e.get("fol", []):
        if x[1] == 1 and x[4] == 0 and x[3] <= 150 and x[5] in ROW: B.append((x[0], x[3], ROW[x[5]]))
def desc(rows):
    svc = collections.Counter(); tips = []; prio = []; direct = 0
    for r in rows:
        t = r.get("tips") or []
        s = sorted({TIP.get(a, "other") for a, _ in t}) if t else ["none"]
        svc["+".join(s)] += 1
        if t: tips.append(sum(v for _, v in t) / 1e9)
        prio.append(max((r.get("fee") or 0) - 5000, 0) / 1e9)
        direct += int(not (set(r.get("progs") or []) - STD))
    n = len(rows)
    return (f"n {n:5d} | direct pump {direct / n:4.0%} | tip paid {len(tips) / n:4.0%}, median tip {statistics.median(tips) if tips else 0:.5f} | "
            f"median prio fee {statistics.median(prio):.5f} | services {', '.join(f'{k} {v / n:.0%}' for k, v in svc.most_common(5))}")
print("ALL same-slot backrun buys within 150 ms:", desc([r for _, _, r in B]))
for lo, hi in ((0, 10), (10, 25), (25, 50), (50, 100), (100, 150)):
    print(f"  {lo:3d}-{hi:3d} ms:", desc([r for _, d, r in B if lo <= d < hi]))
W = collections.defaultdict(list)
for u, d, r in B: W[u].append((d, r))
print("\nwallets with >=40 backruns, fastest median first:")
for u, v in sorted(((u, v) for u, v in W.items() if len(v) >= 40), key=lambda kv: statistics.median(d for d, _ in kv[1]))[:25]:
    print(f"  {u}  median {statistics.median(d for d, _ in v):5.1f} ms |", desc([r for _, r in v]))
