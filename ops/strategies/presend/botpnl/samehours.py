#!/usr/bin/env python3
"""Same PKT hours on every run (18:00-08:00 PKT, the window the 11-02 recording covers so far): net and trips per bot.
Also our trips with NO bot within 10 slots vs with any bot buying in the same slot or after us. usage: samehours.py OUTDIR"""
import sys, json, glob, os, collections
def pkt_h(bt): return ((bt + 18000) // 3600) % 24
for rd in sorted(glob.glob(f"{sys.argv[1]}/run_*")):
    T = [t for t in json.load(open(f"{rd}/trips.json")) if t.get("bt0") and (pkt_h(t["bt0"]) >= 18 or pkt_h(t["bt0"]) < 8)]
    bt = sorted(t["bt0"] for t in T); hrs = (bt[-1] - bt[0]) / 3600
    by = collections.defaultdict(lambda: [0, 0])
    for t in T: by[t["bot"]][0] += 1; by[t["bot"]][1] += t["sol"]
    bym = collections.defaultdict(list)
    for t in T:
        if t["bot"] != "OURS": bym[t["mint"]].append(t)
    g = collections.defaultdict(lambda: [0, 0])
    for o in (t for t in T if t["bot"] == "OURS"):
        near = [b for b in bym.get(o["mint"], []) if -10 <= b["s0"] - o["s0"] <= 10]
        k = "no bot" if not near else ("bot same/after" if any(b["s0"] >= o["s0"] for b in near) else "bot only before")
        g[k][0] += 1; g[k][1] += o["sol"]
    print(f"{os.path.basename(rd)} 18-08 PKT ({hrs:.1f} h): " + " | ".join(f"{b} {n} {s/1e9:+.2f}" for b, (n, s) in sorted(by.items(), key=lambda kv: -kv[1][1]) if b in ("haqq", "8yYMhu", "E2x1", "OURS", "4ggJqUDD")))
    print("   ours: " + " | ".join(f"{k} n {n} {s/1e9:+.2f} ({s/n/1e6:+.1f} mSOL)" for k, (n, s) in g.items()))
