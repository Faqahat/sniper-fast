#!/usr/bin/env python3
"""BOTREG 5c: skip-if-a-listed-seller-held, split by the rule that listed the holder (rule as of that hour is approximated by the
wallet's final rule set; listing time is causal). DEV first; r55 printed after, all splits pre-listed (no r55 selection)."""
import sys, os, pickle, glob, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
FS = "/home/moiz/sniper-data/flatsig/runs"
chain = {}
for p in sorted(glob.glob(f"{C.DATA}/hourly/*.ours.pkl")):
    for x in pickle.load(open(p, "rb")): chain[(x["mint"], x["slot"], x["w"])] = x
Sz = np.load(f"{C.DATA}/backtest/sellers.npz"); sl = collections.defaultdict(set)
for t, u in zip(Sz["t"], Sz["u"]): sl[int(t)].add(int(u))
reg = pickle.load(open(f"{C.DATA}/backtest/registry_state.pkl", "rb"))
rule = {u: set(r["rule"].split("+")) for u, r in reg.S.items()}
for per, runs in (("DEV", [f"r{i}" for i in range(37, 55)]), ("r55", ["r55"])):
    R = collections.defaultdict(list)
    for run in runs:
        for p in pickle.load(open(f"{FS}/ex_{run}.pkl", "rb"))["pos"]:
            m = C.pk64(p["mint"]); cp = next((chain[k] for k in ((m, p["buy_slot"], w) for w in C.OURS64) if k in chain), None)
            if not cp: continue
            lst = sl.get(C.hour_of(p["t0"] / 1e9), set())
            hr = set().union(*[rule.get(u, set()) for u, pct in cp["holders"] if u in lst]) if cp["holders"] else set()
            for k in ("S1", "S2", "S3", "S4"):
                if k in hr: R[k].append(p["pnl"])
    print(per)
    for k in ("S1", "S2", "S3", "S4"):
        a = np.array(R[k]); sv = np.sort(-a)[::-1]
        if len(a): print(f"  holder listed by {k}: n {len(a):4d} our P&L {a.sum():+.3f} mean {a.mean() * 1e3:+.1f} mSOL | skip saves {sv.sum():+.3f}, w/o top5 {sv.sum() - sv[:5].sum():+.3f}")
