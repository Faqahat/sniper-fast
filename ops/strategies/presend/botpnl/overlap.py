#!/usr/bin/env python3
"""Overlap of OUR trips with the bots' trips (trips.json from analyze.py). Per run: our trips split by which bot bought the
same mint within 10 slots (before us / same slot / after us), our P&L in each group, and the bots' P&L on those shared trips.
Also haqq per wallet. usage: overlap.py OUTDIR"""
import sys, json, glob, os, collections
for rd in sorted(glob.glob(f"{sys.argv[1]}/run_*")):
    T = json.load(open(f"{rd}/trips.json"))
    ours = [t for t in T if t["bot"] == "OURS"]
    bym = collections.defaultdict(list)
    for t in T:
        if t["bot"] != "OURS": bym[t["mint"]].append(t)
    print(f"\n=== {os.path.basename(rd)}: our {len(ours)} trips {sum(t['sol'] for t in ours)/1e9:+.2f}")
    hw = collections.defaultdict(lambda: [0, 0])
    for t in T:
        if t["bot"] == "haqq": hw[t["w"][:8]][0] += 1; hw[t["w"][:8]][1] += t["sol"]
    print("  haqq wallets: " + ", ".join(f"{w} {n} trips {s/1e9:+.2f}" for w, (n, s) in hw.items()))
    grp = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, our sol, bot sol, bot n
    for o in ours:
        tags = []
        for b in bym.get(o["mint"], []):
            d = b["s0"] - o["s0"]
            if -10 <= d <= 10:
                tags.append((b["bot"], "before" if d < 0 else ("same" if d == 0 else "after"), b["sol"]))
        seen = set()
        for bot, where, bs in tags:
            k = (bot, where)
            if k in seen: continue
            seen.add(k); g = grp[k]; g[0] += 1; g[1] += o["sol"]; g[2] += bs
        if not tags: g = grp[("none", "")]; g[0] += 1; g[1] += o["sol"]
    for (bot, where), (n, os_, bs, _) in sorted(grp.items(), key=lambda kv: -kv[1][0]):
        if n < 5: continue
        print(f"  {bot:9s} {where:6s} n {n:4d}  our net {os_/1e9:+6.2f} ({os_/n/1e6:+6.1f} mSOL/trip)  bot net on these {bs/1e9:+6.2f}")
