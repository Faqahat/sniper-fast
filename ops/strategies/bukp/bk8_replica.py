#!/usr/bin/env python3
# REPLICA with the learned EXIT (read-only): BUkpShoE's own entries re-timed to OUR landing (35 / 50 ms after its trigger,
# +5% guard), size = its 2%-of-curve size ("own") or 0.6 SOL, exit = first trade whose exit-model score (bk7_exit.py,
# trained on R2) >= threshold, our sell landing 35 ms after that trade; else the 1,417-slot timeout. Follower slippage
# limits, our costs. All thresholds scored in one pass per day (rows batched). -> bukp/exit_replica.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import gbdt_np as G
import bk7_exit as B7
from multiprocessing import get_context
OUT = "/home/moiz/sniper-data/strategies/bukp"; UID = B7.UID
MD = json.load(open(f"{OUT}/exit_model_trees.json")); EDGES = [np.array(e) for e in MD["edges"]]; THR = {float(k): v for k, v in MD["thr"].items()}
FIX, FAIL, GUARD, GRADV, TOUT = B7.FIX, B7.FAIL, B7.GUARD, B7.GRADV, B7.TOUT

def entry(d, t, lat, size_mode):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] == UID: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None
    fr = float(d["fr"][k0]); B = t["buys"][0]["sol"] * (1 + fr) if size_mode == "own" else 0.6
    ta = d["arr"][j] + lat; land = j + 1
    while land < end and (d["arr"][land] < ta or d["uid"][land] == UID): land += 1
    q = land - 1
    while q >= a and d["uid"][q] == UID: q -= 1
    Vb, Tb = float(d["vsol"][q]), float(d["vtok"][q])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(fail=1, pnl=-FAIL, B=B)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt; p_in = X / qt; s_land = int(ta // 212.0)
    path = [m for m in range(land, end) if d["uid"][m] != UID and d["s"][m] <= s_land + TOUT + 1]
    Vs = []; Ts = []; keep = []
    for m in path:
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt < float(d["tokn"][m]) / (1.0 + float(d["slack"][m])): Vs.append(V); Ts.append(T); keep.append(False); continue
            V += sol; T -= dt
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk
        Vs.append(V); Ts.append(T); keep.append(True)
        if V >= GRADV: break
    path = path[:len(Vs)]
    pk = 1.0; ssum = bsum = 0.0; nsell = 0; rows = []
    for n, m in enumerate(path):
        mlt = (Vs[n] / Ts[n]) / p_in; pk = max(pk, mlt)
        if keep[n]:
            if d["buy"][m]: bsum += d["sol"][m] / 1e9
            else: ssum += d["sol"][m] / 1e9; nsell += 1
        rows.append((m, mlt, pk, int(d["s"][m] - s_land), 1 - mlt / pk, ssum, bsum, nsell))
    return dict(fail=0, B=B, qt=qt, fr=fr, s_land=s_land, path=path, Vs=Vs, Ts=Ts, rows=rows, V0=V if not path else None, T0=None, small=t["buys"][0]["sol"] < 1.0)

def run_day(args):
    run, lat, size_mode = args
    d = E.DAYS[run]; T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    ents = [entry(d, t, lat, size_mode) for t in T]
    allrows = []; owner = []
    for n, e in enumerate(ents):
        if e and not e["fail"] and e["rows"]:
            allrows += e["rows"]; owner += [n] * len(e["rows"])
    idx, X = B7.features(d, allrows); sc = B7.predict(MD["trees"], MD["lr"], B7.binm(X, EDGES)); owner = np.array(owner)
    out = {}
    for q, th in THR.items():
        p_all = []; p_small = []; nto = 0; nfail = 0; holds = []
        hits = {}
        ok = np.flatnonzero((sc >= th) & (np.array([r[3] for r in allrows]) >= 0))
        for h in ok:
            o = int(owner[h])
            if o not in hits: hits[o] = h
        start = {}
        for h, o in enumerate(owner):
            if int(o) not in start: start[int(o)] = h
        for n, e in enumerate(ents):
            if e is None: continue
            if e["fail"]: p_all.append(e["pnl"]); nfail += 1; continue
            path, Vs, Ts = e["path"], e["Vs"], e["Ts"]
            if not path:
                pnl = -FIX - e["B"] * (1 - (1 - e["fr"]) / (1 + e["fr"]))
            elif n in hits:
                pos = hits[n] - start[n]; m = path[pos]; ta2 = d["arr"][m] + lat; nn = pos
                while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta2: nn += 1
                got = Vs[nn] * e["qt"] / (Ts[nn] + e["qt"]) * (1 - e["fr"]) / 1e9; pnl = got - e["B"] - FIX; holds.append(int(d["s"][m] - e["s_land"]))
            else:
                nn = len(path) - 1
                while nn > 0 and d["s"][path[nn]] > e["s_land"] + TOUT: nn -= 1
                got = Vs[nn] * e["qt"] / (Ts[nn] + e["qt"]) * (1 - e["fr"]) / 1e9; pnl = got - e["B"] - FIX; nto += 1; holds.append(TOUT)
            p_all.append(pnl)
            if e["small"]: p_small.append(pnl)
        out[q] = dict(n=len(p_all), pnl=round(sum(p_all), 2), mean=round(float(np.mean(p_all)), 4), win=round(float(np.mean([x > 0 for x in p_all])), 3), fails=nfail, timeouts=nto,
                      small_n=len(p_small), small_pnl=round(sum(p_small), 2), small_mean=round(float(np.mean(p_small)), 4) if p_small else None,
                      hold_med=float(np.median(holds)) if holds else None)
    return (run, lat, size_mode), out

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    jobs = [(r, lat, sm) for r in days for lat in (35, 50) for sm in ("own", "0.6")]
    res = {}
    with get_context("fork").Pool(6) as p:
        for key, out in p.imap_unordered(run_day, jobs):
            res["|".join(map(str, key))] = out
    json.dump(res, open(f"{OUT}/exit_replica.json", "w"), indent=1)
    for q in sorted(THR):
        print(f"exit thr q{q}:")
        for sm in ("own", "0.6"):
            for lat in (35, 50):
                print(f"   size {sm:<3} {lat}ms: " + " | ".join(f"{r} n {res[f'{r}|{lat}|{sm}'][q]['n']} pnl {res[f'{r}|{lat}|{sm}'][q]['pnl']:+7.2f} mean {res[f'{r}|{lat}|{sm}'][q]['mean']:+.4f} (curve<50: {res[f'{r}|{lat}|{sm}'][q]['small_pnl']:+.1f}) timeouts {res[f'{r}|{lat}|{sm}'][q]['timeouts']}" for r in days))
