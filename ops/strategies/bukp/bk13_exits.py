#!/usr/bin/env python3
# EXIT FAMILIES on BUkpShoE's entries re-timed to OUR landing (35 ms after its trigger, 0.6 SOL; its own trades removed:
# we take its place), split into GRADUATION-BOUND trips (the token's curve later completes) vs the rest (descriptive split,
# uses the future). Benchmark = its own exit moment. Families (fills 35 ms after the deciding trade):
#   ts_all(T)    trailing stop: price <= (1-T) x peak-since-entry, checked on every trade
#   ts_sell(T)   same, checked only when another wallet's SELL prints ("first sell print after drawdown >= T")
#   + time caps 60 / 120 / 180 / 300 s, min hold 0 / 15 slots
#   tp ladder    50% at 1.2x, 50% at 1.5x (else trailing ts_sell(0.10)), cap 300 s (partials approximated on the path)
#   to_grad      hold until the curve completes (fill at the last pre-graduation state) or the cap
# -> bukp/exit_families.json
import sys, json, zlib, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import bk8_replica as B8
from multiprocessing import get_context
OUT = "/home/moiz/sniper-data/strategies/bukp"; UID = B8.UID
CAPS = {"60s": 283, "120s": 566, "180s": 849, "300s": 1417}
FAMS = []
for T in (0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
    for chk in ("all", "sell"):
        for cap in ("60s", "120s", "180s", "300s"):
            for mh in (0, 15):
                FAMS.append(dict(kind="ts", T=T, chk=chk, cap=CAPS[cap], mh=mh, name=f"ts_{chk}{int(T * 100)}_{cap}_mh{mh}"))
for cap in ("120s", "300s"):
    FAMS.append(dict(kind="ladder", cap=CAPS[cap], name=f"ladder_1.2_1.5_{cap}"))
    FAMS.append(dict(kind="to_grad", cap=CAPS[cap], name=f"to_grad_{cap}"))
    FAMS.append(dict(kind="timer", cap=CAPS[cap], name=f"timer_{cap}"))

def proceeds(e, n, frac=1.0):
    q = e["qt"] * frac
    return e["Vs"][n] * q / (e["Ts"][n] + q) * (1 - e["fr"]) / 1e9

def fill_index(d, e, n, lat=35):
    path = e["path"]; ta = d["arr"][path[n]] + lat; nn = n
    while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta: nn += 1
    return nn

def run_family(d, e, F):
    path, rows = e["path"], e["rows"]
    if not path: return -B8.FIX - e["B"] * (1 - (1 - e["fr"]) / (1 + e["fr"])), 0
    last = len(path) - 1
    def cap_index():
        nn = last
        while nn > 0 and d["s"][path[nn]] > e["s_land"] + F["cap"]: nn -= 1
        return nn
    if F["kind"] == "timer" or F["kind"] == "to_grad":
        nn = cap_index(); return proceeds(e, nn) - e["B"] - B8.FIX, rows[nn][3]
    if F["kind"] == "ladder":
        got = 0.0; left = 1.0; done = set()
        for n, r in enumerate(rows):
            if r[3] > F["cap"]: break
            if 0 not in done and r[1] >= 1.2: got += proceeds(e, fill_index(d, e, n), 0.5); left -= 0.5; done.add(0)
            if 1 not in done and r[1] >= 1.5: got += proceeds(e, fill_index(d, e, n), left); left = 0; done.add(1); break
            if r[4] >= 0.10 and not d["buy"][path[n]] and r[3] >= 15: got += proceeds(e, fill_index(d, e, n), left); left = 0; break
        if left > 0: got += proceeds(e, cap_index(), left)
        return got - e["B"] - B8.FIX, None
    for n, r in enumerate(rows):
        if r[3] > F["cap"]: break
        if r[3] < F["mh"]: continue
        if F["chk"] == "sell" and d["buy"][path[n]]: continue
        if r[4] >= F["T"]:
            nn = fill_index(d, e, n); return proceeds(e, nn) - e["B"] - B8.FIX, r[3]
    nn = cap_index(); return proceeds(e, nn) - e["B"] - B8.FIX, rows[nn][3]

def day(run):
    d = E.DAYS[run]; T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    res = {"own": {"grad": [], "other": []}}
    for F in FAMS: res[F["name"]] = {"grad": [], "other": []}
    holds = {F["name"]: [] for F in FAMS}; own_hold = []
    for t in T:
        e = B8.entry(d, t, 35, "0.6")
        if e is None: continue
        grp = "grad" if t["grad"] else "other"
        if e["fail"]:
            for k in res: res[k][grp].append(e["pnl"])
            continue
        if not e["path"]: continue
        ks = t["sells"][-1]["k"]; nn = None
        for n, m in enumerate(e["path"]):
            if m < ks: nn = n
            else: break
        nn = 0 if nn is None else nn
        res["own"][grp].append(proceeds(e, nn) - e["B"] - B8.FIX)
        for F in FAMS:
            p, h = run_family(d, e, F); res[F["name"]][grp].append(p)
            if h is not None: holds[F["name"]].append(abs(h - t["hold"]))
    out = {k: dict(grad=(len(v["grad"]), round(sum(v["grad"]), 2)), other=(len(v["other"]), round(sum(v["other"]), 2)),
                   hold_dev_med=int(np.median(holds[k])) if k in holds and holds[k] else None) for k, v in res.items()}
    return run, out

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    with get_context("fork").Pool(3) as p:
        R = dict(p.map(day, days))
    json.dump(R, open(f"{OUT}/exit_families.json", "w"))
    print("P&L at 35 ms, 0.6 SOL, our costs: (trips, SOL) on GRADUATION-BOUND trips | other trips  [median |exit slot - its exit slot|]")
    print(f"  {'its own exit':<26} " + " || ".join(f"{r}: grad {R[r]['own']['grad']} other {R[r]['own']['other']}" for r in days))
    best = sorted(FAMS, key=lambda F: -(R["R2"][F["name"]]["grad"][1] + R["R2"][F["name"]]["other"][1]))[:12]
    bestg = sorted(FAMS, key=lambda F: -R["R2"][F["name"]]["grad"][1])[:12]
    print("best on R2 (all trips):")
    for F in best:
        print(f"  {F['name']:<26} " + " || ".join(f"{r}: grad {R[r][F['name']]['grad'][1]:+7.2f} other {R[r][F['name']]['other'][1]:+7.2f} dev {R[r][F['name']]['hold_dev_med']}" for r in days))
    print("best on R2 graduation-bound trips:")
    for F in bestg:
        print(f"  {F['name']:<26} " + " || ".join(f"{r}: grad {R[r][F['name']]['grad'][1]:+7.2f} other {R[r][F['name']]['other'][1]:+7.2f} dev {R[r][F['name']]['hold_dev_med']}" for r in days))
