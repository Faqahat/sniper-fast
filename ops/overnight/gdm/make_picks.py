#!/usr/bin/env python3
# GDM step 5a: pick lists for the official evaluator (core/become_eval.py). Thresholds = validation (fold2) quantiles.
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
Z, M = common.load(); bt = Z["bt"]; run = Z["run"]; mints = np.array(M["mints"]); guard = Z["guard"] == 1
f2p = np.load(f"{common.OUT}/f2.npz")["pick"]; TEND = bt.max()
def masks(d):
    a = "R1" if d == "fwd" else "R2"; idx = np.where(run == a)[0]; o = idx[np.argsort(bt[idx], kind="stable")]; c8 = bt[o[int(len(o) * 0.8)]]
    return (run == a) & (bt >= c8), run == ("R2" if d == "fwd" else "R1")
P = {}
for d, lab, fs, q in (("fwd", "yc", "LM", 0.02), ("fwd", "E3", "LM", 0.05), ("fwd", "ya", "LM", 0.03), ("fwd", "yc", "LM", 0.03),
                      ("rev", "E3", "LM", 0.075), ("rev", "yc", "LM", 0.03), ("rev", "ya", "LM", 0.03), ("rev", "E3", "LM", 0.05)):
    VA, TE = masks(d); f = np.load(f"{common.OUT}/models/cv_{d}_f2_{lab}_{fs}.npy")
    thr = np.quantile(f[VA], 1 - q); P[f"{d}_{lab}_{fs}_q{q}"] = sorted(mints[TE & (f >= thr) & guard])
    t50 = np.quantile(f[VA], 0.5); P[f"{d}_{lab}_{fs}_F2veto"] = sorted(mints[TE & f2p & (f >= t50)])
P["F2off_R2"] = sorted(mints[(run == "R2") & f2p]); P["F2off_R1"] = sorted(mints[(run == "R1") & f2p])
live = json.load(open(f"{common.CORE}/final2_picks_v3.json")); LS = json.load(open(f"{common.CORE}/gf_launches.json"))
P["F2live_R2"] = sorted(m for m in live if m in LS and LS[m]["bt"] <= TEND)
for k, v in P.items(): json.dump(v, open(f"{common.OUT}/picks/{k}.json", "w"))
c2 = sorted(set().union(*[set(v) for k, v in P.items() if k.startswith("fwd") or k.endswith("R2")]))
c1 = sorted(set().union(*[set(v) for k, v in P.items() if k.startswith("rev") or k.endswith("R1")]))
json.dump(c2, open(f"{common.OUT}/picks/cand_R2.json", "w")); json.dump(c1, open(f"{common.OUT}/picks/cand_R1.json", "w"))
print({k: len(v) for k, v in P.items()}, "cand R2", len(c2), "cand R1", len(c1))
