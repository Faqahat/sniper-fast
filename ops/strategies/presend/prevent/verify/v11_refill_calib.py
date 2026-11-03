#!/usr/bin/env python3
"""VERIFY step 11: calibration of GUARDS' replay on the windows its guard changes: replay base P&L vs the LIVE realized P&L (scaled, mine)
of the same windows; hybrid estimate = -(live P&L of changed fills) + (replay guard P&L of those windows)."""
import json, pickle, collections
D = "/home/moiz/sniper-data/prevent/guards"; OUT = "/home/moiz/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb"))
RM = {"f26": "F26", "f27": "F27", "f28": "F28", "r34": "A34", "r35": "A35", "r36": "A36", "r37": "A37"}
tw = {(x["run"], x["w"]): x for x in T["trades"]}
G = collections.Counter()
for run, mine in RM.items():
    d = json.load(open(f"{D}/rp_{run}_sign0.15_open.json")); reps = d["reps"]
    acc = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for b_rows, g_rows in zip(d["base"], d["guard"]):
        for b, g in zip(b_rows, g_rows):
            a = acc[(b[0], b[1])]; a[0] += b[3] / reps; a[1] += g[3] / reps; a[2] += b[4] / reps; a[3] += g[4] / reps
    best = max((0, 1, 2), key=lambda off: sum(1 for (ses, w), v in acc.items() if v[0] > 0.5 and (mine, (ses + off, w)) in tw))
    acc = {(ses + best, w): v for (ses, w), v in acc.items()}
    n = m = 0; live_sum = rb = rg = 0.0; nlive_unmatched = 0; base_vs_live = []
    for (ses, w), (bf, gf, bp, gp) in acc.items():
        x = tw.get((mine, (ses, w)))
        if x: base_vs_live.append((bp, x["s"]))
        if bf > 0.5 and abs(gp - bp) > 1e-9:          # the guard changed a filled window
            if x is None: nlive_unmatched += 1; continue
            n += 1; live_sum += x["s"]; rb += bp; rg += gp
    cal_b = sum(a for a, b in base_vs_live); cal_l = sum(b for a, b in base_vs_live)
    hybrid = -live_sum + rg
    print(f"{mine}: changed filled windows {n} (unmatched {nlive_unmatched}) | live P&L of them {live_sum:+.3f} vs replay base {rb:+.3f} | replay guard P&L {rg:+.3f}"
          f" | replay delta {rg - rb:+.3f} vs hybrid {hybrid:+.3f} | all matched fills: replay base {cal_b:+.3f} vs live {cal_l:+.3f} (n {len(base_vs_live)})")
    G["n"] += n; G["live"] += live_sum; G["rb"] += rb; G["rg"] += rg; G["cb"] += cal_b; G["cl"] += cal_l
print({k: round(v, 3) for k, v in G.items()}, "replay delta", round(G["rg"] - G["rb"], 3), "hybrid", round(-G["live"] + G["rg"], 3))
