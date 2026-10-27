#!/usr/bin/env python3
# POST-MIGRATION STUDY: dip-backrun on PumpSwap at our speed and cost (R2 = choose, R3 = test, R4 = check).
#  trigger: a sell of >= SELL SOL that moves the pool price by <= -DROP, token age (since migration) in [AGE0, AGE1] s,
#           token type filter; one trigger per token per hold window.
#  entry:   trigger arrival + LAT ms; guard: price at landing <= GUARD x price right after the trigger, else failed buy.
#  exit:    timer HOLD s after landing, or TP (pool price multiple of our fill) with a max hold.
#  cost:    0.0035 SOL per round trip (FIX) or a lean 0.0005; failed buy 0.0005. Pool fees: the pool's own bps.
import sys, os, json, itertools, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import pmsim
from pmsim import Run, SMS, one_at_a_time, stats
OUT = "/home/moiz/sniper-data/strategies/postmig"
HOURS = {"R2": 21.8, "R3": 25.0, "R4": None}

def typ(t):
    if t["mayhem"]: return "mayhem"
    if t.get("age_s") is not None and t["age_s"] <= 1.0: return "instant"
    return "fast" if (t.get("age_s") or 1e9) < 300 else "slow"

def prep(run):
    r = Run(run)
    R = r.R
    gtype = np.array([typ(r.tok_of_grp[g]) if g in r.tok_of_grp else "?" for g in range(len(r.gstart))])
    migs = np.array([r.tok_of_grp[g]["mig_s"] if g in r.tok_of_grp else 0 for g in range(len(r.gstart))])
    r.gtype = gtype
    r.age = (R["s"] - migs[r.rank]) * SMS / 1000
    r.drop = R["p_post"] / R["p_pre"] - 1
    r.sol = R["qtot"] / 1e9
    hrs = HOURS.get(run) or (r.end_slot - min(t["mig_s"] for t in r.toks)) * SMS / 3.6e6
    r.hours = hrs
    return r

def triggers(r, sell, drop, age0, age1, types, gap_ms):
    R = r.R
    m = (R["side"] == -1) & (r.sol >= sell) & (r.drop <= -drop) & (r.age >= age0) & (r.age <= age1) & np.isin(r.gtype[r.rank], types)
    idx = np.nonzero(m)[0]
    if len(idx) == 0: return idx
    # one trigger per token per gap window
    keep = []; last = {}
    for j, g, a in zip(idx.tolist(), r.rank[idx].tolist(), R["arr"][idx].tolist()):
        if g in last and a - last[g] < gap_ms: continue
        last[g] = a; keep.append(j)
    return np.array(keep, np.int64)

def run_rule(r, P, lat, fix=pmsim.FIX):
    idx = triggers(r, P["sell"], P["drop"], P["age0"], P["age1"], P["types"], P["hold"] * 1000 + 500)
    if len(idx) == 0: return None, None
    g = r.rank[idx]; t = r.R["arr"][idx]; pref = r.R["p_post"][idx]
    old = pmsim.FIX; pmsim.FIX = fix
    try:
        if P.get("tp"):
            res = r.sim(g, t, pref, size=P["size"], lat=lat, guard=P["guard"], tp=P["tp"], sl=P.get("sl"), max_ms=P["hold"] * 1000)
        else:
            res = r.sim(g, t, pref, size=P["size"], lat=lat, guard=P["guard"], hold_ms=P["hold"] * 1000)
    finally:
        pmsim.FIX = old
    ok = ~res["cens"]
    res = {k: v[ok] for k, v in res.items()}
    take = one_at_a_time(res)
    return res, take

GRID = dict(sell=[0.5, 1.0, 2.0, 4.0], drop=[0.02, 0.04, 0.08], age=[(0, 60), (0, 600), (60, 3600), (0, 86400)],
            types=[("instant",), ("fast", "slow"), ("instant", "fast", "slow")], hold=[1.5, 3, 6, 15], guard=[1.02, 1.05])

def grid():
    for s, d, a, ty, h, gd in itertools.product(GRID["sell"], GRID["drop"], GRID["age"], GRID["types"], GRID["hold"], GRID["guard"]):
        yield dict(sell=s, drop=d, age0=a[0], age1=a[1], types=ty, hold=h, guard=gd, size=0.5)

if __name__ == "__main__":
    t0 = time.time()
    mode = sys.argv[1] if len(sys.argv) > 1 else "search"
    if mode == "search":
        r2 = prep("R2"); print("R2 ready", f"{time.time()-t0:.0f}s", flush=True)
        rows = []
        for n, P in enumerate(grid()):
            res, take = run_rule(r2, P, 35.0)
            if res is None: continue
            s_all = stats(res, hours=r2.hours); s_one = stats(res, take, hours=r2.hours)
            res8, take8 = run_rule(r2, P, 8.0)
            s8 = stats(res8, take8, hours=r2.hours)
            rows.append(dict(P=P, all35=s_all, one35=s_one, one8=s8))
        json.dump(rows, open(f"{OUT}/dip_search_R2.json", "w"))
        print("variants", n + 1, "evaluated", len(rows), f"{time.time()-t0:.0f}s")
        rows.sort(key=lambda x: -x["one35"]["pnl"])
        for x in rows[:25]:
            print(x["P"], "| one35", x["one35"], "| all35", {k: x["all35"][k] for k in ("n", "pnl", "mean", "win")}, "| one8", {k: x["one8"][k] for k in ("n", "pnl", "mean")})
