#!/usr/bin/env python3
# READ-ONLY: print the classified buy sequence of a few creates from buyers.jsonl (after analyze.py)
# usage: inspect_mint.py [n_creates | mint ...]
import json, sys, collections, random
B = [json.loads(l) for l in open("/root/indep/buyers.jsonl")]
bm = collections.defaultdict(list)
for b in B:
    bm[b["mint"]].append(b)
args = sys.argv[1:]
if args and not args[0].isdigit():
    mints = args
else:
    n = int(args[0]) if args else 6
    random.seed(int(args[1]) if len(args) > 1 else 1)
    cand = [m for m, bs in bm.items() if sum(1 for b in bs if b["sd"] == 0) >= 2]
    mints = random.sample(cand, min(n, len(cand)))
for m in mints:
    bs = sorted(bm[m], key=lambda b: b["rank"])
    b0 = bs[0]
    print(f"\n{m} slot {b0['cslot']} client {b0['cclient']} creator {b0['creator'][:8]} dev {b0['dev']/1e9:.2f} SOL")
    for b in bs[:14]:
        flags = "".join(k for k in ("a", "b", "c", "d", "e") if b.get(k)) + ("J" if b.get("jito_bundle") else "") + ("T" if b.get("same_tip_as_create") else "")
        print(f"  r{b['rank']:<2d} sd{b['sd']} off{b['off']:<4d} {b['user'][:8]} {b['sender'][:22]:22s} sol {b['sol']/1e9:6.3f} fill {b['fill']:.3f} "
              f"np {str(b.get('n_prior')):>4s} age {str(round(b['age_s']/60) if b.get('age_s') is not None else '-'):>5s}m "
              f"L{b['n_launch']}/C{b['n_creators']} [{flags:6s}] {b['cls']}")
