#!/usr/bin/env python3
# COPY ITS EXIT LIVE (read-only): we trade ALONGSIDE BUkpShoE on its tokens. Our buy lands 35 / 50 ms after its trigger
# (its own buy stays in the tape, usually landing after ours); we sell when we SEE its sell: our sell lands 1 slot (212 ms)
# or 35 ms after its sell transaction, i.e. after its ~3.5% sell impact. Size 0.6 SOL; +5% guard; follower slippage limits
# for every later buy (its own included); our costs. Split by graduation-bound vs other tokens. -> bukp/copy_exit.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/bukp"
UID = zlib.crc32(b"BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP")
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9

def copy_trade(d, t, lat_in, lat_out, B=0.6):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] == UID: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None
    fr = float(d["fr"][k0])
    ta = d["arr"][j] + lat_in; land = j + 1
    while land < end and d["arr"][land] < ta: land += 1
    Vb, Tb = float(d["vsol"][land - 1]), float(d["vtok"][land - 1])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(fail=1, pnl=-FAIL)
    X = B * 1e9 / (1 + fr); q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
    ks = t["sells"][-1]["k"]; t_exit = d["arr"][ks] + lat_out
    m = land
    while m < end and (m <= ks or d["arr"][m] < t_exit):
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt >= float(d["tokn"][m]) / (1.0 + float(d["slack"][m])):
                if V + sol >= GRADV: break
                V += sol; T -= dt
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk
        m += 1
    got = V * q / (T + q) * (1 - fr) / 1e9
    return dict(fail=0, pnl=got - B - FIX, ahead_of_it=bool(land <= k0))

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    out = {}
    for run in days:
        d = E.DAYS[run]; T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
        for lin in (35, 50):
            for lout in (212, 35):
                g = []; o = []; ahead = []
                for t in T:
                    r = copy_trade(d, t, lin, lout)
                    if r is None: continue
                    (g if t["grad"] else o).append(r["pnl"])
                    if not r.get("fail"): ahead.append(r["ahead_of_it"])
                key = f"{run}|in{lin}|out{lout}"
                out[key] = dict(grad=(len(g), round(sum(g), 2), round(float(np.mean(g)), 4) if g else None), other=(len(o), round(sum(o), 2), round(float(np.mean(o)), 4) if o else None),
                                total=round(sum(g) + sum(o), 2), ahead_share=round(float(np.mean(ahead)), 3))
                print(f"{key}: graduation-bound {out[key]['grad']} | other {out[key]['other']} | total {out[key]['total']:+.2f} | our buy lands ahead of its buy {out[key]['ahead_share']:.0%}", flush=True)
    json.dump(out, open(f"{OUT}/copy_exit.json", "w"), indent=1)
