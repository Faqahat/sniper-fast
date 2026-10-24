#!/usr/bin/env python3
# Can we run GKd5EMzR's scalping at our speed? (owner 10-24 ~22:40 PKT: "Can we try it?"). Replay on the recorded days.
# GKd5EMzR: ~0.28 SOL buys, holds ~6 s, many round trips per busy token, net +0.35%/SOL, costs ~0.00014 SOL per round trip.
# Entry sets: "its" = the trade right before each of its buys (<= 2 slots; its own trades removed from the tape), landing
#   15 ms (about its speed) / 35 / 50 ms; "copy" = every trade >= 0.5 SOL (buy or sell) on tokens >= 300 slots old with
#   curve 37-79 SOL and >= 30 trades (its trigger profile), landing 35 / 50 ms.
# Exits: timers 5 / 10 / 30 / 60 slots (1-13 s) and TP/SL pairs. Size 0.28 SOL. Engine = sssss/ss8_sim (+5% guard, follower
# slippage limits). Costs: pump fee both sides + FIX per round trip: 0.00014 (its level), 0.001, 0.0035 (ours).
# Many positions at once (as it trades) and one at a time (our engine). R2 = train, R3 / R1 = test.
import sys, json, zlib
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/gkd5"
W = "GKd5EMzRhbprZXZfsbJczo4SrfF99XZWQA82bazaQr14"; UID = zlib.crc32(W.encode())
EXITS = {"sell after 1 s": {"max_slots": 5}, "sell after 2 s": {"max_slots": 10}, "sell after 6 s": {"max_slots": 30}, "sell after 13 s": {"max_slots": 60},
         "TP +3% / SL -3% / 6 s": {"tp": 1.03, "sl": 0.97, "max_slots": 30}, "TP +5% / SL -5% / 13 s": {"tp": 1.05, "sl": 0.95, "max_slots": 60}}
DAYS = ["R2", "R3", "R1"]; FIX = 0.0035; FIXES = (0.00014, 0.001, 0.0035)
G_ = {}
def setup():
    E.load(DAYS); SETS = {}; rng = np.random.default_rng(3)
    for run in DAYS:
        d = E.DAYS[run]; F = d["F"]; FI = d["FI"]
        d["sibs"] = np.full(len(d["s"]), -10 ** 9, np.int64)
        me = np.flatnonzero((d["uid"] == UID) & (d["buy"] == 1))
        its = []
        for k in me:
            j = k - 1
            while j >= 0 and d["uid"][j] == UID: j -= 1
            if j >= 0 and d["tok"][j] == d["tok"][k] and d["s"][k] - d["s"][j] <= 2: its.append(int(j))
        cu = F[:, FI["curve"]]
        copy = np.flatnonzero((d["uid"] != UID) & (d["sol"] >= 0.5e9) & (F[:, FI["age"]] >= 300) & (cu >= 37) & (cu <= 79) & (F[:, FI["ntr"]] >= 30))
        samp = np.sort(rng.choice(copy, size=min(len(copy), 15000), replace=False)) if len(copy) else copy
        SETS[run] = dict(its=np.array(sorted(set(its)), np.int64), copy=copy, copy_s=samp)
        print(f"{run}: its buys {len(me)}, its triggers {len(SETS[run]['its'])}, copy-rule moments {len(copy)}", flush=True)
    G_["SETS"] = SETS
def task(a):
    run, setname, ex, lat, one = a
    d = E.DAYS[run]; S_ = G_["SETS"][run]
    ks = S_["its"] if setname == "its" else (S_["copy"] if one else S_["copy_s"])
    rs = S.run_entries(d, ks, lat, 0.28, S.norm_exit(EXITS[ex]), FIX, one, UID if setname == "its" else None, d["sibs"])
    ok = [r for r in rs if not r["fail"]]; nf = len(ok)
    base = sum(r["pnl"] for r in rs)
    out = {f: base + nf * (FIX - f) for f in FIXES}
    scale = (len(S_["copy"]) / max(1, len(S_["copy_s"]))) if (setname == "copy" and not one) else 1.0
    return a, dict(n=nf, fail=len(rs) - nf, pnl={f: v * scale for f, v in out.items()}, win=sum(1 for r in ok if r["pnl"] > 0) / max(1, nf), scale=scale)
if __name__ == "__main__":
    setup()
    jobs = [(r, "its", ex, lat, one) for r in DAYS for ex in EXITS for lat in (15, 35, 50) for one in (False, True)]
    jobs += [(r, "copy", ex, lat, one) for r in DAYS for ex in EXITS for lat in (35, 50) for one in (False, True)]
    res = {}
    with get_context("fork").Pool(8) as p:
        for a, v in p.imap_unordered(task, jobs): res[a] = v
    json.dump({"|".join(map(str, k)): {**v, "pnl": {str(f): x for f, x in v["pnl"].items()}} for k, v in res.items()}, open(f"{OUT}/gk1.json", "w"))
    for setname, lats in (("its", (15, 35, 50)), ("copy", (35, 50))):
        for one in (False, True):
            print(f"\n=== {'its own buy moments' if setname == 'its' else 'copy rule: any >=0.5 SOL trade, token >=1 min old, curve 37-79'} | {'one position at a time' if one else 'many positions'}" + (" (sampled 15k/day, scaled)" if setname == "copy" and not one else ""))
            print(f"  {'exit':<24} {'land':>5} | {'R2 (train)':^34} | {'R3 (test)':^34} | {'R1 (test)':^34}")
            print(f"  {'':<24} {'':>5} | " + " | ".join(f"{'its fee':>9} {'0.001':>8} {'ours':>8} {'n':>5}" for _ in DAYS))
            for ex in EXITS:
                for lat in lats:
                    cells = []
                    for r in DAYS:
                        v = res[(r, setname, ex, lat, one)]
                        cells.append(f"{v['pnl'][0.00014]:+9.1f} {v['pnl'][0.001]:+8.1f} {v['pnl'][0.0035]:+8.1f} {v['n']:5d}")
                    print(f"  {ex:<24} {lat:>3}ms | " + " | ".join(cells))
    print("\nSOL per day after pump fees and the per-round-trip cost shown (its 0.00014 / 0.001 / ours 0.0035); n = filled trades")
