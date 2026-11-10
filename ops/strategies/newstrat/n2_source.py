#!/usr/bin/env python3
"""NEWSTRAT step 2: MONEY SOURCE. Who pays 9pQQ / 8PgC / E2x1 / us?
(a) wallet classes per run from the tape: trade count on the run + P&L (closed positions realized, open bags marked at the mint's
    last curve price after fee) -> BOTW (>= 300 trades, P&L > 0), BOTL (>= 300, <= 0), MID (30-299), RET (< 30), DEV (a creator
    of a launch in the run, on its own token).
(b) for each closed trip of a watched wallet: other wallets' SOL flow on the mint during the hold (buys spend in, sells out) by class,
    split by trip outcome; and by time after the wallet's buy (chain clock).
(c) zero-sum: on the mints where the watched wallet made money on the run, every class's P&L on those mints.
Output OUT/source_<run>.json and a printed table."""
import sys, json
import numpy as np
import nlib as L

BUCKETS = [0, 50, 90, 212, 636, 5300, 53000, 1e12]          # ms after its buy: <50, 50-90, 90-1slot, 1-3 slots, 3-25, 25-250, 250+
BNAMES = ["<50ms", "50-90", "90ms-1sl", "1-3sl", "3-25sl", "25-250sl", "250+sl"]
CL = ["BOTW", "BOTL", "MID", "RET", "DEV"]

def classes(t, la):
    nu, nm = len(t.users), len(t.mints)
    ntr = np.bincount(t.u, minlength=nu)
    key = t.u.astype(np.int64) * nm + t.m
    uk, inv = np.unique(key, return_inverse=True)
    stok = np.bincount(inv, weights=t.tok.astype(np.float64))
    ssol = np.bincount(inv, weights=t.sol.astype(np.float64))
    # last curve balance per mint
    last = t.cpost[t.mstart[1:] - 1].astype(np.float64)
    pm = L.price(last)
    km = uk % nm; ku = uk // nm
    # open bags: on clean mints (launched in the run, not mayhem, not graduated) share the real SOL left in the curve pro rata
    # to tokens held (= liquidation value of all bags together); elsewhere spot mark after fee
    clean = np.zeros(nm, bool)
    for m, v in la.items():
        mi = t.mix.get(m)
        if mi is not None and not v["may"]: clean[mi] = True
    clean &= last > 207.5e12
    held = np.where(stok > 0, stok, 0.0)
    hsum = np.bincount(km, weights=held, minlength=nm)
    real = np.maximum(L.vsol(last) - 30e9, 0.0)
    alloc = np.where(hsum[km] > 0, held / np.maximum(hsum[km], 1.0) * real[km] * (1 - L.FEE), 0.0)
    mtm = np.where(clean[km], alloc, held * pm[km] * (1 - L.FEE))
    pnl_pos = ssol + mtm
    pnl = np.bincount(ku, weights=pnl_pos, minlength=nu)
    c = np.full(nu, 3, np.int8)
    c[ntr >= 30] = 2
    c[(ntr >= 300) & (pnl <= 0)] = 1
    c[(ntr >= 300) & (pnl > 0)] = 0
    creator = {}
    for m, v in la.items():
        mi = t.mix.get(m); ui = t.uix.get(v["creator"])
        if mi is not None and ui is not None: creator[mi] = ui
    return c, pnl, ntr, (uk, ku, km, pnl_pos, clean), creator

def run(run):
    t = L.load(run)
    la = L.launches(run)
    c, pnl, ntr, pos, creator = classes(t, la)
    trips = json.load(open(f"{L.OUT}/trips_{run}.json"))
    res = {"wallet_classes": {CL[k]: dict(n=int((c == k).sum()), pnl=round(float(pnl[c == k].sum()) / 1e9, 1)) for k in range(4)}}
    uk, ku, km, pnl_pos, clean = pos
    cm = np.full(len(t.mints), -1, np.int64)
    for mi, ui in creator.items(): cm[mi] = ui
    for name in ["9pQQ", "8PgC", "E2x1", "OURS"]:
        uid = t.uix.get({"9pQQ": L.W9, "8PgC": L.W8, "OURS": L.OURS, "E2x1": "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"}[name])
        tr = [x for x in trips[name] if x.get("x") is not None and not x["may"]]
        if not tr or uid is None: continue
        # flows during hold: [outcome win/lose][class][bucket] net SOL in (buys - sells)
        F = np.zeros((2, 5, len(BNAMES)))
        G = np.zeros((2, 5))           # gross buys
        nwin = 0
        for x in tr:
            mi = t.mix[x["mint"]]
            a0, a1 = t.mstart[mi], t.mstart[mi + 1]
            b, e = x["b"], x["x"]
            sl = np.arange(b + 1, e)                      # rows strictly between its buy and sell (tape order = s,i)
            if len(sl) == 0: continue
            sl = sl[t.u[sl] != uid]
            if len(sl) == 0: continue
            w = 0 if x["net"] > 0 else 1
            cls = c[t.u[sl]].astype(np.int64).copy()
            cr = creator.get(mi)
            if cr is not None: cls[t.u[sl] == cr] = 4
            dt = t.cc[sl] - t.cc[b]
            bk = np.searchsorted(BUCKETS, dt, side="right") - 1
            flow = -t.sol[sl].astype(np.float64)          # buys: sol<0 -> +inflow; sells: sol>0 -> outflow
            np.add.at(F[w], (cls, bk), flow)
            np.add.at(G[w], cls, np.where(t.tok[sl] > 0, flow, 0.0))
        # zero-sum on mints where it made money this run
        mnet = {}
        for x in tr: mnet[x["mint"]] = mnet.get(x["mint"], 0) + x["net"]
        good = np.array([t.mix[m] for m, v in mnet.items() if v > 0 and clean[t.mix[m]]])
        bad = np.array([t.mix[m] for m, v in mnet.items() if v <= 0 and clean[t.mix[m]]])
        def zs(ms):
            sel = np.isin(km, ms)
            cls = c[ku[sel]].astype(np.int64).copy()
            cls[cm[km[sel]] == ku[sel]] = 4
            out = {CL[k]: round(float(pnl_pos[sel][cls == k].sum()) / 1e9, 2) for k in range(5)}
            out["it"] = round(float(pnl_pos[sel][ku[sel] == uid].sum()) / 1e9, 2)
            return out
        res[name] = dict(trips=len(tr), net=round(sum(x["net"] for x in tr) / 1e9, 2),
                         flow_win={CL[k]: [round(v / 1e9, 1) for v in F[0, k]] for k in range(5)},
                         flow_lose={CL[k]: [round(v / 1e9, 1) for v in F[1, k]] for k in range(5)},
                         gross_buy_win={CL[k]: round(G[0, k] / 1e9, 1) for k in range(5)},
                         gross_buy_lose={CL[k]: round(G[1, k] / 1e9, 1) for k in range(5)},
                         zerosum_good_mints=zs(good), zerosum_bad_mints=zs(bad), n_good=len(good), n_bad=len(bad))
        print(run, name, json.dumps(res[name]), flush=True)
    res["buckets"] = BNAMES
    json.dump(res, open(f"{L.OUT}/source_{run}.json", "w"))

if __name__ == "__main__":
    for r in sys.argv[1:]: run(r)
