#!/usr/bin/env python3
# sssssDdM's OWN trades re-timed to OUR speed (read-only; adapted from bukp/bk5_retime.py, not modified). For every closed
# trip: the trigger = the last NON-FLEET trade before its buy (same token, <= 2 slots; sibling ssssswdk trades are skipped
# when looking for the trigger but stay on the tape as real market trades). We take its place: its own trades are removed
# from the tape; our buy lands (a) where it actually landed (sanity check vs its realized curve P&L), (b) 35 ms or (c) 50 ms
# after the trigger's modelled arrival; +5% price guard vs the price right after the trigger (else a failed buy, -0.0005 SOL);
# size = its size (~1.9% of curve) or capped to 0.35-0.75 SOL; we sell at its exit moment (right before its sell) or, variant
# "x+lat", after the trades that arrive within our latency after the trade that preceded its sell. Follower buys whose
# slippage limit our earlier/extra buy breaks are dropped. Costs: pump fee (event bps) both sides + 0.0035 SOL per round trip.
# -> sssss/retime_<run>.json + printed P&L splits (trigger, size, hold, hour PKT, curve)
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9

def replay(d, t, lat, cap, xlat=False, isfleet=None):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and isfleet[j]: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None                    # no trigger: its own timing, cannot be re-timed
    ks = t["sells"][-1]["k"]
    fr = float(d["fr"][k0])
    B = t["buys"][0]["sol"] * (1 + fr) if cap is None else min(max(t["buys"][0]["sol"] * (1 + fr), cap[0]), cap[1])
    if lat == "own": land = k0
    else:
        ta = d["arr"][j] + lat; land = j + 1
        while land < end and (d["arr"][land] < ta or d["uid"][land] == UID): land += 1
        if land > ks: return dict(ok=0, fail=0, reason="lands after its exit")
    q = land - 1
    while q >= a and d["uid"][q] == UID: q -= 1
    Vb, Tb = float(d["vsol"][q]), float(d["vtok"][q])
    if Vb >= GRADV: return None
    if lat != "own" and (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(ok=0, fail=1, pnl=-FAIL, B=B)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt
    # exit position: right before its sell, or (xlat) after trades arriving within lat after the trade preceding its sell
    xe = ks
    if xlat and lat != "own":
        p = ks - 1
        while p > land and d["uid"][p] == UID: p -= 1
        ta2 = d["arr"][p] + lat; xe = p + 1
        while xe < end and (d["arr"][xe] < ta2 or d["uid"][xe] == UID): xe += 1
        xe = max(xe, ks)
    for m in range(land, xe):
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
    E.load([run]); d = E.DAYS[run]
    isfleet = np.isin(d["uid"], FLEET)
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    res = []
    for t in T:
        last = t["last"] or {}
        r = dict(size=t["buys"][0]["sol"], hold=t["hold"], pnl_actual=t["pnl_curve"], hour=t["state"]["hour"], curve=t["state"].get("curve"),
                 trig_side=last.get("side"), trig_sol=last.get("sol"), trig_dslot=last.get("dslot"), exit_big_sell=t["sells"][-1]["maxs3"] >= 0.5,
                 exit_big_buy=t["sells"][-1]["maxb3"] >= 0.5, sib=bool(t["sibpos"]), mint=t["mint"], slot=t["slot"])
        for lat in ("own", 35, 50):
            for cap in (None, (0.35, 0.75)):
                r[f"{lat}_{'cap' if cap else 'full'}"] = replay(d, t, lat, cap, False, isfleet)
        for lat in (35, 50):
            r[f"{lat}_cap_x"] = replay(d, t, lat, (0.35, 0.75), True, isfleet)
        res.append(r)
    json.dump(res, open(f"{OUT}/retime_{run}.json", "w"))
    del E.DAYS[run]
    return res

def summ(res, key, filt=lambda r: True):
    xs = [r[key] for r in res if filt(r) and r.get(key)]
    ok = [x for x in xs if x.get("ok")]; fl = [x for x in xs if x.get("fail")]
    p = [x["pnl"] for x in ok] + [x["pnl"] for x in fl]
    if not p: return "n 0"
    srt = sorted(p)
    return (f"n {len(xs):5d} filled {len(ok):5d} guard-fail {len(fl):4d} P&L {sum(p):+8.2f} per trip {np.mean(p):+.4f} per SOL {sum(p) / max(1e-9, sum(x['B'] for x in ok)):+.4f} "
            f"win {np.mean([v > 0 for v in p]):.0%} w/o top1% {sum(srt[:-max(1, len(srt) // 100)]):+7.2f}")

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R2", "R3", "R1", "R4"]
    for run in runs:
        res = run_day(run)
        print(f"\n===== {run}: {len(res)} closed trips; its actual curve P&L {sum(r['pnl_actual'] for r in res):+.2f} SOL (excl. tx fees)")
        for key in ("own_full", "own_cap", "35_full", "50_full", "35_cap", "50_cap", "35_cap_x", "50_cap_x"):
            print(f"  {key:<9} {summ(res, key)}")
        for lab, f in (("trigger = buy same slot", lambda r: r["trig_side"] == "B" and r["trig_dslot"] == 0), ("trigger = sell same slot", lambda r: r["trig_side"] == "S" and r["trig_dslot"] == 0),
                       ("trigger 1-2 slots earlier", lambda r: (r["trig_dslot"] or 0) >= 1),
                       ("size <0.8", lambda r: r["size"] < 0.8), ("size 0.8-1.0", lambda r: 0.8 <= r["size"] < 1.0), ("size >=1.0", lambda r: r["size"] >= 1.0),
                       ("hold <30 slots", lambda r: r["hold"] < 30), ("hold 30-300", lambda r: 30 <= r["hold"] < 300), ("hold >=300", lambda r: r["hold"] >= 300),
                       ("exit after big sell", lambda r: r["exit_big_sell"]), ("exit after big buy", lambda r: r["exit_big_buy"] and not r["exit_big_sell"]),
                       ("sibling holds", lambda r: r["sib"]), ("alone", lambda r: not r["sib"]),
                       ("curve <50", lambda r: (r["curve"] or 0) < 50), ("curve >=50", lambda r: (r["curve"] or 0) >= 50)):
            print(f"   {lab:<26} own {summ(res, 'own_full', f)}\n   {'':<26} 35c {summ(res, '35_cap', f)}")
        hrs = collections.defaultdict(list)
        for r in res: hrs[r["hour"] // 3 * 3].append(r)
        print("   by 3h PKT (35 ms, capped size): " + " | ".join(f"{h:02d}h {sum(x['35_cap']['pnl'] for x in v if x.get('35_cap') and 'pnl' in x['35_cap']):+.2f}" for h, v in sorted(hrs.items())))
