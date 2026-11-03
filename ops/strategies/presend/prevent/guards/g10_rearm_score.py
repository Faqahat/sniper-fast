#!/usr/bin/env python3
"""GUARDS step 10: score the re-arm holder guard on the multiarm JOINT replay (all tries phantom = INFERRED, calibrated on r38 live re-arm
fills by the multiarm agent): r37 (paper re-arm; the guard idea came from r38, so r37 is the independent check) and r38 (as far as its ctx
reaches). Rows: off / open / naive, 8 reps each; cash = slip-basis SOL (multiarm's main row), cash_cut = -20% followers.
usage: g10_rearm_score.py"""
import pickle, glob, collections, json
import numpy as np
S = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/prevent/guards/ma"
OUT = "/home/moiz/sniper-data/prevent/guards"
res = {}; lines = []
rng = np.random.default_rng(3)
for run in ("r37", "r38"):
    for g in ("off", "open", "naive", "dump1", "dump3"):
        reps = []
        for f in sorted(glob.glob(f"{S}/{run}_{g}_*.pkl")):
            d = pickle.load(open(f, "rb")); rr = d["res"]; m = d["meta"]
            x = {"rep": d["rep"], "hours": m["hours"]}
            for kind in ("t2", "rearm"):
                v = [r for r in rr if r["kind"] == kind]
                x[kind] = {"fills": sum(r["filled"] for r in v), "cash": sum(r["cash"] for r in v), "cut": sum(r["cash_cut"] for r in v)}
            x["blocked"] = m["stats"].get("guard_blocked", 0)
            x["hour_cash"] = collections.defaultdict(float)
            for r in rr: x["hour_cash"][int(((r["t_arm"] / 1e3) + 5 * 3600) // 3600)] += r["cash"]
            reps.append(x)
        res[(run, g)] = reps
for run in ("r37", "r38"):
    off = {x["rep"]: x for x in res[(run, "off")]}
    if not off: continue
    hrs = next(iter(off.values()))["hours"]
    lines.append(f"== {run} ({hrs:.1f} h, reps {len(off)}): SOL, slip basis; per day = x 24 / hours")
    for g in ("off", "open", "naive", "dump1", "dump3"):
        xs = [x for x in res[(run, g)] if x["rep"] in off]
        if not xs: continue
        def m(f): return float(np.mean([f(x) for x in xs]))
        d_all = [x["t2"]["cash"] + x["rearm"]["cash"] - off[x["rep"]]["t2"]["cash"] - off[x["rep"]]["rearm"]["cash"] for x in xs]
        d_cut = [x["t2"]["cut"] + x["rearm"]["cut"] - off[x["rep"]]["t2"]["cut"] - off[x["rep"]]["rearm"]["cut"] for x in xs]
        # block bootstrap over PKT hours of the paired per-hour delta (mean over reps)
        hk = sorted(set().union(*[set(x["hour_cash"]) for x in xs]))
        hd = np.array([np.mean([x["hour_cash"].get(h, 0) - off[x["rep"]]["hour_cash"].get(h, 0) for x in xs]) for h in hk])
        boots = [hd[rng.integers(len(hd), size=len(hd))].sum() for _ in range(3000)] if len(hd) else [0]
        lines.append(f"{g:6s} re-arm fills {m(lambda x: x['rearm']['fills']):6.1f} cash {m(lambda x: x['rearm']['cash']):+7.3f} | T2 fills {m(lambda x: x['t2']['fills']):6.1f} cash {m(lambda x: x['t2']['cash']):+7.3f} | "
                     f"total {m(lambda x: x['t2']['cash'] + x['rearm']['cash']):+7.3f} | delta vs off {np.mean(d_all):+6.3f} (/day {np.mean(d_all) * 24 / hrs:+5.2f}; reps min {min(d_all):+.3f} max {max(d_all):+.3f}) "
                     f"| -20% delta {np.mean(d_cut):+6.3f} | CI90 hours [{np.percentile(boots, 5):+.2f},{np.percentile(boots, 95):+.2f}] | guard blocks {m(lambda x: x['blocked']):.0f}")
open(f"{OUT}/rearm_guard.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
