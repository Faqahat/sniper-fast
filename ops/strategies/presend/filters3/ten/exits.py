#!/usr/bin/env python3
"""TEN lever (d): EXITS on our REAL fills (live entry kept as it was), replayed on the raw recording (p2 rows, others only; fixed SOL
buys / fixed token sells; our buy at its live block position, our sell moved). Recorded hours only (DEV mostly; VAL 11-01 12:00-19:09).
  LIVE   sell where the live sell landed (check of the replay vs live realized)
  FIX N  sell after the last trade of slot fill + N
  FOLLOW at the live sell slot S: if others bought >= K times in slots S-1..S-1 (seen before the sell is sent), hold to the end of S+1;
         repeat while that holds, cap fill + 8 (signing-time-like: uses only trades before each decision)
Costs as live: the position's own fixed costs, 1.25% each way. Stress: drop 20% of others' buys after our fill (also before decisions)."""
import json, sys, collections, hashlib, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/ten")
from wsim import dedup, Curve, K, OFF, FEE, ME
D = "/home/moiz/sniper-data/filters3/ten/"
H = json.load(open(D + "hours.json"))
tape = {m: dedup(v) for m, v in json.load(open(D + "p2tape.json")).items()}
pos = json.load(open(D + "pos.json"))

def h(s): return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xffffffff

def run(p, rows, policy, drop=0.0):
    f = (p["fill_slot"], p["fill_idx"])
    pre = [r for r in rows if (r[0], r[1] or 0) < f]
    if not pre: return None
    cv = Curve(pre[-1][6] + OFF)
    x_in = p["spend"] * 1e9 / (1 + FEE)
    vt0 = cv.vt; cv.vt = K / (cv.vs + x_in); mytok = vt0 - cv.vt
    post = [r for r in rows if (r[0], r[1] or 0) > f]
    keep = [r for r in post if not (r[6] < r[5] and drop and h(f"{r[0]}:{r[1]}") < drop)]
    sl = p["sell_land"]
    kind, arg = policy
    if kind == "LIVE": sell_at = (sl[0], sl[1])
    elif kind == "FIX": sell_at = (f[0] + arg + 1, -1)
    else:                                            # FOLLOW: decisions on others' buys in slot S-1+2j
        buys = collections.Counter(r[0] for r in keep if r[6] < r[5])
        S = sl[0]; j = 0
        while buys[S - 1 + 2 * j] >= arg and S + 2 * (j + 1) <= f[0] + 9: j += 1
        sell_at = (S, sl[1]) if j == 0 else (S + 2 * j, -1)
    for r in keep:
        if (r[0], r[1] or 0) >= sell_at: break
        cv.apply(r)
    out = K / cv.vt - K / (cv.vt + mytok)
    fees_live = FEE * (p["sol_in"] + p["sol_out_curve"])
    fixed = p["curve_pnl"] - fees_live - p["pnl"]
    return (out - x_in) / 1e9 - FEE * (x_in + out) / 1e9 - fixed

def covered(rows, a, b): return rows and rows[0][0] < a - 5 and rows[-1][0] > b

P = [p for p in pos if (p.get("rounds") or 1) == 1 and p.get("sell_land") and covered(tape.get(p["mint"]), p["fill_slot"], p["fill_slot"] + 12)]
print("positions replayable:", collections.Counter(p["seg"] for p in P))
pols = [("LIVE", None), ("FIX", 1), ("FIX", 2), ("FIX", 3), ("FIX", 5), ("FIX", 8), ("FOLLOW", 1), ("FOLLOW", 2), ("FOLLOW", 3)]
for drop in (0.0, 0.2):
    print(f"\n== others' later buys dropped {drop:.0%}")
    for sg in ("DEV", "VAL"):
        Q = [p for p in P if p["seg"] == sg]
        live = sum(p["pnl"] for p in Q)
        base = None
        for pol in pols:
            v = [run(p, [r for r in tape[p["mint"]] if r[2] != ME], pol, drop) for p in Q]
            v = [x for x in v if x is not None]
            tot = sum(v); vs = sorted(v, reverse=True)
            if pol[0] == "LIVE": base = tot
            print(f"  {sg} n {len(v)} {pol[0]:6s} {str(pol[1]):4s} replay {tot:+7.3f} ({1000 * tot / len(v):+5.1f} mSOL/fill, w/o top5 {sum(vs[5:]):+7.3f}) vs LIVE-replay {tot - base:+6.3f}   [live realized {live:+.3f}]")
