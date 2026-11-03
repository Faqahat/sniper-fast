#!/usr/bin/env python3
"""TIMING step 10: score the custom37 replays (t8): per window gain = variant - base P&L (same rep/world), mean over reps, @0.696.
PICK = f26 f27 f28 r34 r35 r36, TEST = r37.  Pass-bar stats + the -20% followers row.  Out: replay.json"""
import json, collections, sys
import numpy as np
D = "/home/moiz/sniper-data/prevent/timing/rp"
RUNS = ["f26", "f27", "f28", "r34", "r35", "r36", "r37"]
data = {r: json.load(open(f"{D}/rp_{r}.json")) for r in RUNS}
VARS = data["r37"]["vars"]
rng = np.random.default_rng(0)


def per_window(r, v, cut):
    """{(ses,w): (t_trig, mean gain, mean base pnl)} averaged over reps"""
    B = data[r]["rows"][f"none|{cut}"]; X = data[r]["rows"][f"{v}|{cut}"]
    acc = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
    for rb, rx in zip(B, X):
        for a, b in zip(rb, rx):
            k = (a[0], a[1]); z = acc[k]; z[0] += b[4] - a[4]; z[1] += a[4]; z[2] = a[2]; z[3] += 1
    return {k: (z[2], z[0] / z[3], z[1] / z[3]) for k, z in acc.items()}


res = {}
print(f"{'variant':12s} | {'PICK':>7s} {'r37':>7s} | runs+/- | {'CI90 PICK+TEST':>16s} | {'w/o1':>6s} {'w/o5':>6s} | {'-20% PICK':>9s} {'-20% r37':>8s} | base PICK / r37 | verdict")
for v in VARS:
    per = {}; allw = []; cutp = {}
    for r in RUNS:
        pw = per_window(r, v, 0.0); per[r] = sum(x[1] for x in pw.values())
        allw += [(x[0], x[1]) for x in pw.values()]
        cutp[r] = sum(x[1] for x in per_window(r, v, 0.2).values())
    pick = sum(per[r] for r in RUNS[:-1]); test = per["r37"]
    up = sum(1 for r in RUNS[:-1] if per[r] > 1e-9); dn = sum(1 for r in RUNS[:-1] if per[r] < -1e-9)
    hb = collections.defaultdict(float)
    for t, g in allw: hb[int(t // 3_600_000)] += g
    hv = np.array(list(hb.values())); bs = [hv[rng.integers(len(hv), size=len(hv))].sum() for _ in range(2000)]
    ci = (float(np.percentile(bs, 5)), float(np.percentile(bs, 95)))
    gs = sorted((g for _, g in allw), reverse=True); tot = sum(gs)
    s = dict(pick=pick, test=test, runs_up=up, runs_dn=dn, ci=ci, wo1=tot - gs[0], wo5=tot - sum(gs[:5]), cut_pick=sum(cutp[r] for r in RUNS[:-1]),
             cut_test=cutp["r37"], per=per, per_cut=cutp)
    c = [s["test"] > 0, up > dn, ci[0] > 0, s["wo1"] > 0, (s["cut_pick"] + s["cut_test"]) >= 0]
    s["verdict"] = "PASS" if all(c) else ("LEAD" if c[0] and c[3] else "FAIL")
    res[v] = s
    bp = sum(sum(x[4] for x in rb) for r in RUNS[:-1] for rb in data[r]["rows"]["none|0.0"]) / 3
    bt = sum(sum(x[4] for x in rb) for rb in data["r37"]["rows"]["none|0.0"]) / 3
    print(f"{v:12s} | {pick:+7.3f} {test:+7.3f} | {up:2d}/{dn:2d}   | [{ci[0]:+6.2f},{ci[1]:+6.2f}] | {s['wo1']:+6.2f} {s['wo5']:+6.2f} | {s['cut_pick']:+9.3f} {s['cut_test']:+8.3f} | {bp:+6.2f} / {bt:+5.2f} | {s['verdict']}")
print("\nper run gain (replay, mean of 3 worlds):")
print("run  " + " ".join(f"{v:>11s}" for v in VARS))
for r in RUNS: print(f"{r:4s} " + " ".join(f"{res[v]['per'][r]:+11.3f}" for v in VARS))
json.dump(res, open("/home/moiz/sniper-data/prevent/timing/replay.json", "w"), indent=1)
