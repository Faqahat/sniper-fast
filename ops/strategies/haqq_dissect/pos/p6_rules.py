#!/usr/bin/env python3
"""pos step 6 (read-only, offline): position rules on top of the DV8 replay machinery, walk-forward per test day.
Machinery reused unchanged (imported): dv8 uni.npz (candidates, rank landing draws, exact follower P&L), g1_walkforward (load,
calibration bootstrap, GBDT gate training recipe), mayhem excluded, usable hours only. 0.40 SOL, +5% guard, K=3 open lots,
all leaders (far +30 ms INFERRED), calibrated = 0.61 x model - 1.17 mSOL per fire (live fit), costs NOW / CHEAP as g1.

Gates (GBDT per exit, trained on days < D-1, exit + threshold chosen on D-1 only, test D read once):
  base = DV8's 28 causal features;
  bg   = base + battleground features (k-th dump on the token, previous dump's window closed?, previous dump's ideal result, slots
         since it, number / sum of earlier paying dumps on the token (closed windows only), haqq bought the previous dump).
  BGR  = no model: k in a range & previous dump's ideal result >= x (grid chosen on D-1).
Position policies:
  ONCE   = one filled buy per token, ever;
  REPEAT = a new buy on a token only when we hold none of it (= DV8 / M2 one-position-per-token);
  ADD    = up to 2 open lots per token (an add on the next picked dump while holding).  Overlapping lots on one token are
           re-simulated JOINTLY on the tape (our first lot's buy and sell move the curve the add trades on) -- exact model.
Out: p6.txt, p6.json"""
import json, sys, time, heapq, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import g1_walkforward as GW
import dd_gbdt as G
import dv8lib as L
from plib import Out, OUT, day_name

P = Out(f"{OUT}/p6.txt")
SIZE = 0.4; FEE = 0.0125
QS = GW.QS; EXITS = GW.EXITS


class Tape:
    def __init__(s):
        ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]
        T = np.load(f"{L.TAB}/trades.npy"); T = T[~np.isin(T["user"], our)]
        o = np.argsort(T["mint"], kind="stable"); T = T[o]
        s.sl = T["slot"].astype(np.int64); s.bu = T["buy"].astype(bool); s.so = T["sol"] / 1e9; s.tk = T["tok"].astype(np.float64)
        s.vs = T["vsol"] / 1e9; s.vt = T["vtok"].astype(np.float64)
        del T

    def qrow(s, r0, end, es, H):
        """last row in [r0, end) with slot <= es+H (>= r0-1)"""
        a, b = r0, end
        hi = a + int(np.searchsorted(s.sl[a:b], es + H, side="right"))
        return max(hi - 1, r0 - 1)

    def joint(s, lots, fol=1.0):
        """lots: list of (r, q) entry row (buy inserted before row r) and exit row (sell after row q). Exact model, sequential."""
        r_min = min(r for r, q in lots); q_max = max(q for r, q in lots)
        V = float(s.vs[r_min - 1]); Tt = float(s.vt[r_min - 1]); K = V * Tt
        tok = [0.0] * len(lots); out = [None] * len(lots)
        sn = SIZE / (1 + FEE)
        buys_at = collections.defaultdict(list); sells_at = collections.defaultdict(list)
        for i, (r, q) in enumerate(lots): buys_at[r].append(i); sells_at[q].append(i)
        for row in range(r_min, q_max + 1):
            for i in buys_at.get(row, []):
                V += sn; T2 = K / V; tok[i] = Tt - T2; Tt = T2
            # row itself
            if s.bu[row]: V += float(s.so[row]) * fol; Tt = K / V
            else: Tt += float(s.tk[row]); V = K / Tt
            for i in sells_at.get(row, []):
                if lots[i][0] > row: continue      # its buy comes later (no trade after it): handled below
                T2 = Tt + tok[i]; V2 = K / T2; out[i] = (V - V2) * (1 - FEE) - SIZE; V, Tt = V2, T2
        # lots whose exit is r-1 (no trade after entry): sell right after buy
        for i, (r, q) in enumerate(lots):
            if out[i] is None:
                if r > q_max or tok[i] == 0.0:     # never bought inside the loop (no trade after the entry): buy now
                    V += sn; T2 = K / V; tok[i] = Tt - T2; Tt = T2
                T2 = Tt + tok[i]; V2 = K / T2; out[i] = (V - V2) * (1 - FEE) - SIZE; V, Tt = V2, T2
        return out


def battleground_feats(M, P5):
    k = P5["k"].astype(float); prev = P5["prev"]; ok = P5["prev_ok"]; pay = P5["prev_pay"]; gap = P5["gap"].astype(float)
    N = len(M)
    f_prev_pay = np.where(ok, pay, np.nan)
    f_gap = np.where(prev >= 0, gap, np.nan)
    f_open = np.where(prev >= 0, (~ok).astype(float), np.nan)
    # earlier candidates on the token whose 5-slot window closed: count paying (ideal >= +5%) and sum of ideal P&L
    ideal = P5["ideal"]
    o = np.lexsort((M["cc"], M["mint"])); ms = M["mint"][o]; sl = M["slot"][o].astype(np.int64)
    first = np.r_[True, ms[1:] != ms[:-1]]; starts = np.flatnonzero(first); ends = np.r_[starts[1:], len(o)]
    npay = np.zeros(N); spay = np.zeros(N)
    for a, b in zip(starts, ends):
        if b - a < 2: continue
        s_ = sl[a:b]; e_ = s_ + 5; p_ = np.nan_to_num(ideal[o[a:b]])
        nclosed = np.searchsorted(e_, s_, side="left")          # earlier rows with exit slot < this slot
        cp = np.r_[0, np.cumsum(p_ >= 0.02)]; cs = np.r_[0, np.cumsum(p_)]
        npay[o[a:b]] = cp[nclosed]; spay[o[a:b]] = cs[nclosed]
    hq = M["hq"]
    f_prev_hq = np.where((prev >= 0) & (gap > 2), hq[np.maximum(prev, 0)].astype(float), np.nan)
    return np.vstack([k, f_open, f_prev_pay, f_gap, npay, spay, f_prev_hq]).T.astype(np.float64), \
        ["k", "prev_open", "prev_pay", "gap", "n_pay_prior", "sum_pay_prior", "prev_hq"]


class Rep2:
    def __init__(s, d, tape):
        s.d = d; s.M = d["M"]; s.FILL = d["FILL"]; s.PN = d["PN"]; s.HS = list(d["HS"]); s.names = list(d["names"])
        s.ranks = [i for i, n in enumerate(s.names) if n.startswith("rank")]
        s.cc = s.M["cc"]; s.mint = s.M["mint"].astype(np.int64); s.tape = tape
        Z = np.load(f"{L.D}/uni.npz"); s.R = Z["R"]; s.ES = Z["ES"]; s.end = s.M["end"]
        s.cache = {}

    def run(s, mask, hi, K=3, policy="REPEAT", fol=0, model="rank"):
        m = mask & np.isfinite(s.PN[:, 0, hi, 0])
        idx = np.flatnonzero(m); idx = idx[np.argsort(s.cc[idx])]
        cols = s.ranks if model == "rank" else [s.names.index(model)]
        hold = s.HS[hi] * 212.0 + 300.0
        maxpm = 2 if policy == "ADD" else 1
        res = []
        for c in cols:
            fill = s.FILL[idx, c]; pn = s.PN[idx, c, hi, fol].astype(np.float64)
            ok = fill & np.isfinite(pn)
            take = np.zeros(len(idx), bool); heap = []; openm = collections.defaultdict(list); ever = set()
            groups = []                                        # overlapping filled lots on one mint: list of positions in idx
            for kk, i in enumerate(idx):
                t = s.cc[i]
                while heap and heap[0][0] <= t:
                    _, mm, pos = heapq.heappop(heap); openm[mm].remove(pos)
                mt = s.mint[i]
                if len(heap) >= K or len(openm[mt]) >= maxpm: continue
                if policy == "ONCE" and mt in ever: continue
                take[kk] = True
                if ok[kk]:
                    if openm[mt]: groups.append(openm[mt] + [kk])
                    heapq.heappush(heap, (t + hold, mt, kk)); openm[mt].append(kk); ever.add(mt)
            pnx = np.where(ok, pn, 0.0)
            nadd = 0
            if groups:
                # merge chains (a lot can overlap two others in sequence) into clusters
                par = {}
                def f(x):
                    while par.get(x, x) != x: x = par[x]
                    return x
                for g in groups:
                    for x in g[1:]: par[f(x)] = f(g[0])
                cl = collections.defaultdict(set)
                for g in groups:
                    for x in g: cl[f(x)].add(x)
                for root, mem in cl.items():
                    mem = sorted(mem); nadd += len(mem) - 1
                    key = (tuple(int(idx[x]) for x in mem), c, hi, fol)
                    if key not in s.cache:
                        lots = []
                        for x in mem:
                            i = int(idx[x]); r = int(s.R[i, c]); q = s.tape.qrow(r, int(s.end[i]), int(s.ES[i, c]), s.HS[hi])
                            lots.append((r, q))
                        s.cache[key] = s.tape.joint(lots, fol=GW_FOLS[fol])
                    for x, v in zip(mem, s.cache[key]): pnx[x] = v
            res.append(dict(idx=idx[take], fill=ok[take], pn=np.where(ok[take], pnx[take], 0.0), nadd=nadd))
        return res


GW_FOLS = (1.0, 0.95, 0.90, 0.80)


def money(res, cost, a=1.0, b=0.0, calib=True):
    cb, cs, cf = GW.COST[cost]; tot = []
    for r in res:
        nf = r["fill"].sum(); n = len(r["fill"])
        g = (a * r["pn"].sum() + b * n) if calib else r["pn"].sum()
        tot.append(g - nf * (cb + cs) - (n - nf) * cf)
    return float(np.mean(tot))


def main():
    t0 = time.time()
    d = GW.load(); M = d["M"]; X = d["X"].astype(np.float64); day = d["day"]; us = d["usable"]
    tape = Tape(); R = Rep2(d, tape)
    (A0, B0), BS = GW.calib_boot()
    # self-test: the joint simulator on a single lot must reproduce uni's exact P&L
    rng = np.random.default_rng(0); errs = []
    cand = np.flatnonzero(d["FILL"][:, 2] & np.isfinite(d["PN"][:, 2, 0, 0]))
    for i in rng.choice(cand, 300, replace=False):
        r = int(R.R[i, 2]); q = tape.qrow(r, int(R.end[i]), int(R.ES[i, 2]), 5)
        errs.append(tape.joint([(r, q)])[0] - float(d["PN"][i, 2, 0, 0]))
    P(f"self-test joint vs uni exact (300 lots): max |diff| {1000 * np.max(np.abs(errs)):.4f} mSOL, mean {1000 * np.mean(errs):+.4f}")
    P5 = np.load(f"{OUT}/p5.npz")
    XB, nb = battleground_feats(M, P5)
    X2 = np.hstack([X, XB])
    P(f"# Position rules, walk-forward (DV8 machinery); battleground features {nb}; calibration live = {A0:.2f} x model {1000 * B0:+.2f} mSOL/fire ({time.time() - t0:.0f}s)")
    rk = R.ranks; Y = {}
    for hi in EXITS:
        v = np.where(d["FILL"][:, rk], d["PN"][:, rk, hi, 0], 0.0)
        bad = ~np.isfinite(d["PN"][:, 0, hi, 0])
        Y[hi] = np.where(bad, np.nan, np.nanmean(np.where(np.isfinite(v), v, 0.0), axis=1))

    def cal(res, cost, q=None):
        if q is None: return money(res, cost, A0, B0)
        return float(np.percentile([money(res, cost, a, b) for a, b in BS[::10]], q))

    days = sorted(set(day[us].tolist()))
    tests = [k for k in days if k - 1 in days and any(dd < k - 1 for dd in days)]
    pay = np.where(P5["prev_ok"], P5["prev_pay"], np.nan); kk = P5["k"]
    J = {}
    for D in tests:
        tr = us & (day < D - 1); va = us & (day == D - 1); te = us & (day == D)
        tri = np.flatnonzero(tr); tri = tri[np.argsort(M["bt"][tri])]; cut = int(0.8 * len(tri))
        SC = {}
        for gname, XX in (("base", X), ("bg", X2)):
            E = G.edges_of(XX, tri); Bn = G.binize(XX, E); SC[gname] = {}
            for hi in EXITS:
                y = Y[hi]; okk = np.isfinite(y)
                f_ = tri[:cut][okk[tri[:cut]]]; v_ = tri[cut:][okk[tri[cut:]]]
                mdl = G.fit(Bn, np.clip(np.nan_to_num(y), -0.2, 0.2), f_, v_, loss="l2", rounds=600, lr=0.05, depth=4, min_n=300, lam=10.0, sub=0.8, fsub=0.8, seed=2, patience=60)
                SC[gname][hi] = G.predict(mdl, Bn)
                if gname == "bg" and hi == EXITS[0]:
                    imp = G.importance(mdl, XX.shape[1]); top = np.argsort(-imp)[:10]
                    names = list(d["feats"]) + nb
                    P(f"D{D} bg gate (exit {R.HS[hi]}) top features: " + ", ".join(f"{names[j]} {100 * imp[j]:.0f}%" for j in top))
        print(f"D{D} gates trained ({time.time() - t0:.0f}s)", flush=True)
        rows = {}
        for gname in ("base", "bg", "BGR"):
            for pol in ("ONCE", "REPEAT", "ADD"):
                best = None
                if gname == "BGR":
                    grid = [(hi, (a, b, x)) for hi in EXITS for (a, b) in ((2, 3), (2, 5), (2, 999), (3, 999)) for x in (0.02, 0.04, 0.06, 0.1)]
                    mk = lambda part, p: part & (kk >= p[0]) & (kk <= p[1]) & (np.nan_to_num(pay, nan=-1) >= p[2])
                else:
                    grid = [(hi, q) for hi in EXITS for q in QS]
                    mk = lambda part, q, g=gname: part & (SC[g][hi_] >= np.quantile(SC[g][hi_][va], q))
                for hi, p in grid:
                    hi_ = hi
                    if gname == "BGR": m = mk(va, p)
                    else: m = va & (SC[gname][hi] >= np.quantile(SC[gname][hi][va], p))
                    v = cal(R.run(m, hi, K=3, policy=pol), "NOW")
                    if best is None or v > best[0]: best = (v, hi, p)
                vb, hi, p = best
                if gname == "BGR": pk = te & (kk >= p[0]) & (kk <= p[1]) & (np.nan_to_num(pay, nan=-1) >= p[2]); th = p
                else:
                    th = float(np.quantile(SC[gname][hi][va], p)); pk = te & (SC[gname][hi] >= th)
                rs = R.run(pk, hi, K=3, policy=pol)
                row = dict(val=vb, exit=R.HS[hi], par=str(p), picks=int(pk.sum()), fires=float(np.mean([len(r["fill"]) for r in rs])),
                           fills=float(np.mean([r["fill"].sum() for r in rs])), adds=float(np.mean([r["nadd"] for r in rs])),
                           ideal=money(R.run(pk, hi, K=3, policy=pol, model="ideal"), "NOW", calib=False), ours=money(rs, "NOW", calib=False),
                           cal=cal(rs, "NOW"), cal_lo=cal(rs, "NOW", 5), cal_hi=cal(rs, "NOW", 95), cal_ch=cal(rs, "CHEAP"), cal_ch_lo=cal(rs, "CHEAP", 5))
                rr = R.run(pk, hi, K=3, policy=pol, fol=2); row["f10"] = cal(rr, "NOW"); row["f10_ch"] = cal(rr, "CHEAP")
                rows[(gname, pol)] = row
                P(f"D{D} {gname:4s} {pol:6s} exit {row['exit']:2d} par {row['par']:>14s}: val {vb:+.2f} | picks {row['picks']:,} fires {row['fires']:.0f} fills {row['fills']:.0f} adds {row['adds']:.0f} | "
                  f"ideal {row['ideal']:+.2f} ours {row['ours']:+.2f} cal {row['cal']:+.2f} [{row['cal_lo']:+.2f}..{row['cal_hi']:+.2f}] cheap {row['cal_ch']:+.2f} | f10 {row['f10']:+.2f}/{row['f10_ch']:+.2f} ({time.time() - t0:.0f}s)")
        J[D] = rows
    json.dump({str(D): {f"{g}|{p}": r for (g, p), r in rows.items()} for D, rows in J.items()}, open(f"{OUT}/p6.json", "w"), indent=1, default=float)
    P("\n## Walk-forward per test day: calibrated NOW (SOL/day window) [5-95% calibration bootstrap] / CHEAP / -10% followers NOW / CHEAP")
    P("| rule | " + " | ".join(day_name(D) for D in J) + " | sum D2-D5 NOW | sum D2-D5 CHEAP | days > 0 NOW |")
    P("|---|" + "---|" * (len(J) + 3))
    for g in ("base", "bg", "BGR"):
        for pol in ("ONCE", "REPEAT", "ADD"):
            cells = []; sn = 0; sc = 0; pos = 0
            for D, rows in J.items():
                r = rows[(g, pol)]
                cells.append(f"{r['cal']:+.2f} [{r['cal_lo']:+.2f}..{r['cal_hi']:+.2f}] / {r['cal_ch']:+.2f} / {r['f10']:+.2f} / {r['f10_ch']:+.2f} (ex {r['exit']}, fills {r['fills']:.0f}, adds {r['adds']:.0f})")
                if 2 <= D <= 5: sn += r["cal"]; sc += r["cal_ch"]; pos += r["cal"] > 0
            P(f"| {g} {pol} | " + " | ".join(cells) + f" | {sn:+.2f} | {sc:+.2f} | {pos}/4 |")
    P("\nideal / ours (uncalibrated) NOW per day:")
    for g in ("base", "bg", "BGR"):
        for pol in ("ONCE", "REPEAT", "ADD"):
            P(f"- {g} {pol}: " + "; ".join(f"D{D} {rows[(g, pol)]['ideal']:+.2f} / {rows[(g, pol)]['ours']:+.2f}" for D, rows in J.items()))
    P.save()


if __name__ == "__main__":
    main()
