#!/usr/bin/env python3
# READ-ONLY offline analysis of blockpos_*.json: for every sampled block, where do
# transactions tipping each sender land (non-vote position fraction), split by leader client.
import json, sys, collections, statistics

d = json.load(open(sys.argv[1]))
blocks = d["blocks"]
pos = collections.defaultdict(list)          # (client, prov) -> [frac]
front = collections.defaultdict(collections.Counter)  # client -> prov counts in first 25%
allc = collections.defaultdict(collections.Counter)   # client -> prov counts overall
nblk = collections.Counter()
for b in blocks:
    seq = b.get("provseq") or []
    n = len(seq)
    if n < 20:
        continue
    c = b["client"]
    nblk[c] += 1
    for i, p in enumerate(seq):
        pos[(c, p)].append(i / n)
        allc[c][p] += 1
        if i < n * 0.25:
            front[c][p] += 1
print("blocks per leader client:", dict(nblk))
provs = sorted({p for (_, p) in pos if p != "none"}, key=lambda p: -sum(len(pos[(c, p)]) for c in nblk))
print("\nmedian non-vote position fraction (0=top of block) of txs tipping each sender; n in ()")
hdr = f"{'sender':22s}" + "".join(f"{c[:14]:>16s}" for c in nblk)
print(hdr)
for p in provs[:16] + ["none"]:
    row = f"{p:22s}"
    for c in nblk:
        v = pos.get((c, p), [])
        row += f"{(f'{statistics.median(v):.2f} ({len(v)})' if len(v) >= 5 else '-'):>16s}"
    print(row)
print("\nshare of the FIRST 25% of non-vote txs by sender tipped (vs share of all non-vote txs)")
for c in nblk:
    tf = sum(front[c].values()); ta = sum(allc[c].values())
    top = ", ".join(f"{p} {100*k/tf:.0f}% (all {100*allc[c][p]/ta:.0f}%)" for p, k in front[c].most_common(6))
    print(f"  {c:18s} {top}")
