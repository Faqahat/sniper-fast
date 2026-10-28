#!/usr/bin/env python3
"""base replay vs live (FRA r28, AMS r34, AMS r35) over the same trigger time range"""
import sys, pickle, collections, time
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
import rep
W = rep.W
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
CFG = {"f28": ("rep45", 450_000_000, 0.1), "a34": ("rep45", 450_000_000, 0.1), "a35": ("main", 650_000_000, 0.2)}
for run, (tag, size, tp) in CFG.items():
    L = pickle.load(open(f"{W}/live_{run}.pkl", "rb")); R = L["R"]
    ts = [a["trig"]["t"] / 1e9 for a in R["arms"].values()] + [s["trig"]["t"] / 1e9 for s in R["skips"]]
    t0, t1 = min(ts), min(max(ts), rep.END)
    lf = [f for f in L["fills"] if t0 <= f["t"] / 1e9 <= t1]
    lnet = sum((f["pnl"] or 0) + f["rent"] for f in lf) / 1e9 - L["ffee"] / 1e9
    larm = sum(1 for a in R["arms"].values() if t0 <= a["trig"]["t"] / 1e9 <= t1)
    lq = sum(1 for s in R["skips"] if s.get("why") == "quiet")
    # replay
    arms = []; fills = []; nets = []; fails = []
    for D in (6, 7):
        dy = rep.Day(D, tag)
        for d in dy.draws:
            rows = [r for r in dy.out["base"][d]["rows"] if t0 <= r["bt"] <= t1]
            if d >= len(arms): arms.append(0); fills.append(0); nets.append(0.0); fails.append(0)
            arms[d] += sum(1 for r in rows if r["armed"]); fills[d] += sum(1 for r in rows if r.get("filled"))
            for r in rows:
                if not r["armed"]: continue
                fails[d] += r["nfail"]
                nets[d] += -r["nfail"] * 5000 + ((r["grid"][(size, tp, 0.0)] - 2_015_000) if r.get("filled") else 0)
    nets = np.array(nets) / 1e9
    print(f"{run} {pkt(t0)}->{pkt(t1)} ({(t1 - t0) / 3600:.1f} h) size {size/1e9} tp {tp}: LIVE arms {larm} quiet-skips {lq} fills {len(lf)} net {lnet:+.3f} "
          f"failed tries {L['nfail']} | REPLAY arms {np.mean(arms):.0f} fills {np.mean(fills):.1f} net(2.015 mSOL/trip) {nets.mean():+.3f} "
          f"[draws {nets.min():+.3f}..{nets.max():+.3f}] (2.9 mSOL/trip {nets.mean() - np.mean(fills) * 0.000885:+.3f}) failed tries {np.mean(fails):.0f}")
