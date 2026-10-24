#!/usr/bin/env python3
# COPY-TRADE test (read-only): we buy when WE SEE sssssDdM's buy (our buy lands 35 / 50 ms after its buy tx) and sell when we
# see its sell (35 / 50 ms after its sell tx). Its trades stay on the tape (it is a real market participant ahead of us).
# +5% guard vs the price right after its buy; size 1.88% of curve capped 0.35-0.75 SOL; follower slippage limits; our costs.
# -> printed per day
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9
def copy(d, t, lat):
    k0 = t["k0"]; ks = t["sells"][-1]["k"]; end = int(d["tend"][k0]); fr = float(d["fr"][k0])
    ta = d["arr"][k0] + lat; land = k0 + 1
    while land < end and d["arr"][land] < ta: land += 1
    Vb, Tb = float(d["vsol"][land - 1]), float(d["vtok"][land - 1])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][k0]) / float(d["vtok"][k0])) > GUARD: return dict(fail=1, pnl=-FAIL)
    B = min(max(0.0188 * Vb / 1e9, 0.35), 0.75); X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt
    tx = d["arr"][ks] + lat; m = land
    while m < end and d["arr"][m] < tx:
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt >= float(d["tokn"][m]) / (1.0 + float(d["slack"][m])):
                V += sol; T -= dt
                if V >= GRADV: break
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk
        m += 1
    got = V * qt / (T + qt) * (1 - fr) / 1e9
    return dict(fail=0, pnl=got - B - FIX, B=B)
for run in sys.argv[1:] or ["R2", "R3", "R1"]:
    E.load([run]); d = E.DAYS[run]
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    for lat in (35, 50):
        rs = [r for r in (copy(d, t, lat) for t in T) if r]; p = np.array([r["pnl"] for r in rs])
        print(f"{run} copy {lat} ms: n {len(rs)} guard-fail {sum(r['fail'] for r in rs)} P&L {p.sum():+.2f} mean {p.mean():+.4f} win {(p > 0).mean():.0%} "
              f"w/o top1% {np.sort(p)[:-max(1, len(p) // 100)].sum():+.2f}; at its fee level {p.sum() + 0.00325 * sum(1 for r in rs if not r['fail']):+.2f}", flush=True)
    del E.DAYS[run]
