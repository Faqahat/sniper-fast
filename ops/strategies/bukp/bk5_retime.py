#!/usr/bin/env python3
# BUkpShoE's OWN trades re-timed to OUR speed (read-only). For every closed trip: the trigger = the last other-wallet
# trade before its buy (same token, <= 2 slots). We take its place: its own trades are removed from the tape; our buy lands
# (a) where it actually landed (sanity check vs its realized curve P&L), (b) 35 ms or (c) 50 ms after the trigger's
# arrival; +5% price guard vs the price right after the trigger (else a failed buy, -0.0005 SOL); size = its size (2% of
# curve) or capped to 0.35-0.75 SOL; we sell at its exit moment (right before its sell). Follower buys whose slippage limit
# our earlier/extra buy breaks are dropped. Costs: pump fee (event bps) both sides + 0.0035 SOL per round trip.
# -> bukp/retime_<run>.json + printed P&L splits
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/bukp"
W = "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP"; UID = zlib.crc32(W.encode())
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9

def replay(d, t, lat, cap):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] == UID: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None                    # no trigger: its own timing, cannot be re-timed
    ks = t["sells"][-1]["k"]
    fr = float(d["fr"][k0])
    B = t["buys"][0]["sol"] * (1 + fr) if cap is None else min(max(t["buys"][0]["sol"] * (1 + fr), cap[0]), cap[1])
    # landing index in the ORIGINAL arrays (we skip its own trades while walking)
    if lat == "own": land = k0
    else:
        ta = d["arr"][j] + lat; land = j + 1
        while land < end and (d["arr"][land] < ta or d["uid"][land] == UID): land += 1
        if land > ks: return dict(ok=0, reason="lands after its exit")
    q = land - 1
    while q >= a and d["uid"][q] == UID: q -= 1
    Vb, Tb = float(d["vsol"][q]), float(d["vtok"][q])
    if Vb >= GRADV: return None
    if lat != "own" and (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(ok=0, fail=1, pnl=-FAIL, B=B)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt
    for m in range(land, ks):
        if d["uid"][m] == UID: continue
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt < float(d["tokn"][m]) / (1.0 + float(d["slack"][m])): continue
            V += sol; T -= dt
            if V >= GRADV: break
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk
    got = V * qt / (T + qt) * (1 - fr) / 1e9
    return dict(ok=1, fail=0, pnl=got - B - FIX, B=B, ahead=int(sum(1 for m in range(j + 1, land) if d["uid"][m] != UID)))

def run_day(run):
    d = E.DAYS[run]
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    res = []
    for t in T:
        r = dict(size=t["buys"][0]["sol"], hold=t["hold"], pnl_actual=t["pnl_curve"])
        k0 = t["k0"]; j = k0 - 1
        while j >= 0 and d["uid"][j] == UID: j -= 1
        r["trig_side"] = "B" if d["buy"][j] else "S"
        for lat in ("own", 35, 50):
            for cap in (None, (0.35, 0.75)):
                x = replay(d, t, lat, cap)
                r[f"{lat}_{'cap' if cap else 'full'}"] = x
        res.append(r)
    json.dump(res, open(f"{OUT}/retime_{run}.json", "w"))
    return res

def summ(res, key, filt=lambda r: True):
    xs = [r[key] for r in res if filt(r) and r.get(key)]
    ok = [x for x in xs if x.get("ok")]; fl = [x for x in xs if x.get("fail")]
    p = [x["pnl"] for x in ok] + [x["pnl"] for x in fl]
    if not p: return "n 0"
    return f"n {len(xs):5d} filled {len(ok):5d} guard-fail {len(fl):4d} P&L {sum(p):+8.2f} per trip {np.mean(p):+.4f} per SOL {sum(p) / max(1e-9, sum(x['B'] for x in ok)):+.4f} win {np.mean([v > 0 for v in p]):.0%}"

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R1", "R2", "R3", "R4"]
    E.load(runs)
    for run in runs:
        res = run_day(run)
        print(f"\n===== {run}: {len(res)} closed trips; its actual curve P&L {sum(r['pnl_actual'] for r in res):+.2f} SOL (excl. tx fees)")
        for key in ("own_full", "35_full", "50_full", "35_cap", "50_cap"):
            print(f"  {key:<9} {summ(res, key)}")
        for lab, f in (("size <1.0 SOL", lambda r: r["size"] < 1.0), ("size >=1.0 SOL", lambda r: r["size"] >= 1.0), ("trigger = buy", lambda r: r["trig_side"] == "B"), ("trigger = sell", lambda r: r["trig_side"] == "S"),
                       ("hold <160 slots", lambda r: r["hold"] < 160), ("hold 160-1380", lambda r: 160 <= r["hold"] < 1380), ("timeout >=1380", lambda r: r["hold"] >= 1380)):
            print(f"   {lab:<16} own {summ(res, 'own_full', f)}\n   {'':<16} 35ms {summ(res, '35_full', f)}")
