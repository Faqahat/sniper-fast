#!/usr/bin/env python3
# GRADUATION-GATED STRATEGY at OUR speed (read-only). Entries = candidate moments (other-wallet trades, curve 30-100 SOL,
# age >= 5, >= 5 trades) whose graduation-model score (bk12_grad.py, N = 5 or 10 min, trained on R2) is in R2's top q;
# one position per token at a time; landing 35 / 50 ms after the trigger, +5% guard, follower slippage limits, size 0.6 SOL
# (its 2%-of-curve rule capped at 0.6), our costs. Exits = families of bk13_exits.py. Chosen on R2, tested on R3, R1.
# Single position (our engine) and unconstrained (one per token). -> bukp/grad_gate.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import bk12_grad as B12
import bk13_exits as B13
from multiprocessing import get_context
OUT = "/home/moiz/sniper-data/strategies/bukp"
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9; MAXH = 1417
EXF = [F for F in B13.FAMS if F["name"] in ("ts_sell20_180s_mh15", "ts_sell15_180s_mh15", "ts_sell10_120s_mh15", "ts_all10_120s_mh15", "ts_sell20_300s_mh15", "ts_sell8_60s_mh15")] + \
      [F for F in B13.FAMS if F["kind"] in ("ladder", "to_grad", "timer")]

def entry_at(d, j, lat, B=0.6):
    a = j - int(d["F"][j, d["FI"]["ntr"]]) + 1; end = int(d["tend"][j]); fr = float(d["fr"][j])
    ta = d["arr"][j] + lat; land = j + 1
    while land < end and d["arr"][land] < ta: land += 1
    Vb, Tb = float(d["vsol"][land - 1]), float(d["vtok"][land - 1])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(fail=1, pnl=-FAIL, B=B)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt; p_in = X / qt; s_land = int(ta // 212.0)
    path = []; Vs = []; Ts = []; rows = []; pk = 1.0; ssum = bsum = 0.0; nsell = 0
    m = land
    while m < end and d["s"][m] <= s_land + MAXH + 1:
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt >= float(d["tokn"][m]) / (1.0 + float(d["slack"][m])):
                if V + sol >= GRADV: break
                V += sol; T -= dt; bsum += sol / 1e9
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk; ssum += d["sol"][m] / 1e9; nsell += 1
        mlt = (V / T) / p_in; pk = max(pk, mlt)
        path.append(m); Vs.append(V); Ts.append(T); rows.append((m, mlt, pk, int(d["s"][m] - s_land), 1 - mlt / pk, ssum, bsum, nsell))
        m += 1
    return dict(fail=0, B=B, qt=qt, fr=fr, s_land=s_land, path=path, Vs=Vs, Ts=Ts, rows=rows)

def run(args):
    run_, N, q, lat = args
    d = E.DAYS[run_]
    z = np.load(f"{OUT}/grad_scores_{run_}_N{N}.npz"); idx, s = z["idx"], z["s"]; gs = B12.grad_slot(d)
    thr = json.load(open(f"{OUT}/grad_gate_thr.json"))[f"N{N}_q{q}"]
    sel = idx[s >= thr]
    sel = sel[np.argsort(d["arr"][sel], kind="stable")]
    graduates = (gs[sel] < 10 ** 12)
    res = {}
    for F in EXF:
        busy = -1.0; tok_busy = {}; single = []; unc = []
        for n, j in enumerate(sel):
            j = int(j); t = int(d["tok"][j]); ta = d["arr"][j] + lat
            free_single = ta >= busy; free_tok = ta >= tok_busy.get(t, -1.0)
            if not (free_single or free_tok): continue
            e = entry_at(d, j, lat)
            if e is None: continue
            if e["fail"]:
                if free_single: single.append((e["pnl"], bool(graduates[n])))
                if free_tok: unc.append((e["pnl"], bool(graduates[n])))
                continue
            p, h = B13.run_family(d, e, F)
            hold = h if h is not None else MAXH
            ex = (e["s_land"] + hold + 1) * 212.0
            if free_single: single.append((p, bool(graduates[n]))); busy = ex
            if free_tok: unc.append((p, bool(graduates[n]))); tok_busy[t] = ex
        def st(L):
            if not L: return dict(n=0)
            p = np.array([x[0] for x in L]); g = np.array([x[1] for x in L])
            return dict(n=len(L), pnl=round(float(p.sum()), 2), mean=round(float(p.mean()), 4), win=round(float((p > 0).mean()), 3), grad_share=round(float(g.mean()), 3),
                        pnl_grad=round(float(p[g].sum()), 2), pnl_other=round(float(p[~g].sum()), 2))
        res[F["name"]] = dict(single=st(single), unc=st(unc))
    return args, dict(n_sel=int(len(sel)), grad_rate=round(float(graduates.mean()), 3) if len(sel) else None, res=res)

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    # thresholds from R2 score quantiles
    thr = {}
    import os
    for N in (5, 10):
        M = json.load(open(f"{OUT}/grad_model_N{N}.json")); edges = [np.array(e) for e in M["edges"]]
        for r in days:
            fn = f"{OUT}/grad_scores_{r}_N{N}.npz"
            if not os.path.exists(fn):
                d = E.DAYS[r]; idx, gs = B12.cands(d)
                s = B12.predict(M["trees"], M["lr"], B12.binm(d["F"][idx][:, [d["FI"][f] for f in M["feats"]]].astype(float), edges))
                np.savez(fn, idx=idx, s=s)
        s = np.load(f"{OUT}/grad_scores_R2_N{N}.npz")["s"]
        for q in (0.001, 0.003, 0.01): thr[f"N{N}_q{q}"] = float(np.quantile(s, 1 - q))
    json.dump(thr, open(f"{OUT}/grad_gate_thr.json", "w"))
    jobs = [(r, N, q, lat) for r in days for N in (5, 10) for q in (0.001, 0.003, 0.01) for lat in (35, 50)]
    out = {}
    with get_context("fork").Pool(5) as p:
        for args, o in p.imap_unordered(run, jobs):
            out["|".join(map(str, args))] = o
    json.dump(out, open(f"{OUT}/grad_gate.json", "w"))
    for N in (5, 10):
        for q in (0.001, 0.003, 0.01):
            k2 = f"R2|{N}|{q}|35"
            best = sorted(out[k2]["res"], key=lambda f: -out[k2]["res"][f]["unc"].get("pnl", -1e9))[:3]
            for f in best:
                line = []
                for r in days:
                    for lat in (35, 50):
                        o = out[f"{r}|{N}|{q}|{lat}"]; u = o["res"][f]["unc"]; s1 = o["res"][f]["single"]
                        line.append(f"{r}@{lat} unc n {u.get('n', 0)} pnl {u.get('pnl', 0):+.1f} mean {u.get('mean', 0):+.4f} grad {o['grad_rate']} | single pnl {s1.get('pnl', 0):+.1f}")
                print(f"N{N} top{q:.1%} {f:<22} " + " || ".join(line), flush=True)
