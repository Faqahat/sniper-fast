#!/usr/bin/env python3
"""BOTS step 5 (read-only): exact-curve replay of EVERY dv8-universe dump on days D1-D6 (usable hours, non-mayhem) at OUR regular landing,
so any imitation gate / threshold / exit can be scored walk-forward afterwards (b6). This is 'our 247/248' in deployment conditions:
haqq stays in the tape (his bots are real competitors and followers); our two wallets' rows are removed.
Entry = the 4 contention-aware rank draws of dv8 uni.npz (R: we land after row R-1; far leaders +30 ms), the u1 tape ordering (trades.npy
minus our wallets, stable-sorted by mint) so uni rows index it directly. Sizes 0.30 and 0.40 SOL.
Guard flag: fill5 = our tokens >= post-dump tokens / 1.05 (the engine's min_out; no-limit always fills). pr = post-dump tokens / ours.
Exits (analyst C's xsim.Pos + x12 ev, MEASURED sell-landing delays): T5, WAVE_REG RIDE(150,300,2000), WAVE_PS RIDE(150,150,1000), MS200,
MS1000, MS2000, MS4000, HISRULE RIDE(424,1000,10000) (C's rule that reproduces 85 % of haqq's exits: from 2 slots, sell at the first 1 s
gap without an outside buy; cap 10 s here). Followers x1.0 / 0.9 / 0.8.
Out: bots/b5.npz  PN[u, draw, size, fol, policy] curve P&L SOL (float32), K, PR, FILL5, ESLOT, ECC, ETOK[u, draw, size]"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
SIZES = (0.30, 0.40); FOLS = (1.0, 0.9, 0.8); HZ = 55
PL = [("T", 5), ("RIDE", 150, 300, 2000), ("RIDE", 150, 150, 1000), ("MS", 200), ("MS", 1000), ("MS", 2000), ("MS", 4000), ("RIDE", 424, 1000, 10000)]
G = {}


def work(job):
    a, e, us = job
    DR, DT, _ = G["D"]
    sl = G["sl"][a:e]; ix = G["ix"][a:e]; bu = G["bu"][a:e]; so = G["so"][a:e]; tk = G["tk"][a:e]; vs = G["vs"][a:e]; vt = G["vt"][a:e]
    fe = G["fee"][a:e]; cc = G["cc"][a:e]
    out = []
    for u in us:
        jd = int(G["row"][u]) - a
        fee = fe[jd] if fe[jd] > 0 else X.FEE
        nd = len(G["rk"])
        PN = np.full((nd, len(SIZES), len(FOLS), len(PL)), np.nan, np.float32)
        K = np.zeros(nd, np.int16); PR = np.zeros((nd, len(SIZES)), np.float32); F5 = np.zeros((nd, len(SIZES)), bool)
        ES = np.zeros(nd, np.int64); EC = np.zeros(nd); ET = np.zeros((nd, len(SIZES)))
        for di, c in enumerate(G["rk"]):
            g = max(int(G["R"][u, c]) - 1 - a, jd)
            K[di] = g - jd; ES[di] = sl[g]; EC[di] = cc[g] + 0.01
            hi = int(np.searchsorted(sl, sl[g] + HZ, side="right"))
            js = np.arange(g + 1, hi)
            for si, size in enumerate(SIZES):
                sn = size / (1 + fee)
                tokd = vt[jd] - vs[jd] * vt[jd] / (vs[jd] + sn)
                te = vt[g] - vs[g] * vt[g] / (vs[g] + sn)
                PR[di, si] = tokd / max(te, 1); F5[di, si] = te >= tokd / 1.05; ET[di, si] = te
                c0 = cc[g] + 0.01
                p = dict(kind="reg", V0=float(vs[g]), T0=float(vt[g]), sin=float(sn), cost=size, fee=float(fee), off_in_slot=float(c0 - sl[g] * X.SMS),
                         dcc=(cc[js] - c0).astype(np.float64), bu=bu[js].copy(), so=so[js].copy(), tk=tk[js].copy())
                for fi, fol in enumerate(FOLS):
                    S = Pos(p, fol)
                    for pi, pol in enumerate(PL): PN[di, si, fi, pi] = (ev(S, pol, DR, DT) - 1) * size
        out.append((u, PN, K, PR, F5, ES, EC, ET))
    return out


def main():
    t0 = time.time()
    ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; names = list(U["names"])
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    may = np.load(f"{L.D}/mayhem.npy")
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); hs = (bt + 18000) // 3600 * 3600 - 18000
    day = (bt - L.DAY0) // 86400
    sel = np.isin(hs, list(good)) & ~may & (day >= 1)
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    user = np.asarray(T["user"]); keep = ~np.isin(user, our); del user
    mt = np.asarray(T["mint"])[keep]
    o = np.argsort(mt, kind="stable")
    for c, f in (("slot", np.int64), ("idx", np.int64), ("sol", np.float64), ("tok", np.float64), ("vsol", np.float64), ("vtok", np.float64)):
        G[{"slot": "sl", "idx": "ix", "sol": "so", "tok": "tk", "vsol": "vs", "vtok": "vt"}[c]] = np.asarray(T[c])[keep][o].astype(f)
    G["so"] /= 1e9; G["vs"] /= 1e9
    G["bu"] = np.asarray(T["buy"])[keep][o].astype(bool)
    G["fee"] = (np.asarray(T["fee_bps"])[keep][o].astype(np.float64) + np.asarray(T["cfee_bps"])[keep][o]) / 1e4
    mts = mt[o]; del mt, o
    G["cc"] = L.cc(G["sl"], G["ix"])
    # check: uni rows index this ordering
    chk = np.flatnonzero(sel)[:2000]
    assert (G["sl"][M["row"][chk]] == M["slot"][chk]).all() and (G["ix"][M["row"][chk]] == M["idx"][chk]).all(), "uni row mismatch"
    G["row"] = M["row"]; G["R"] = U["R"]; G["rk"] = rk; G["D"] = delays()
    um, st = np.unique(mts, return_index=True); en = np.append(st[1:], len(mts))
    spans = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    del mts
    print(f"tape ready {len(G['sl']):,} rows; candidates {sel.sum():,} ({time.time() - t0:.0f}s)", flush=True)
    byk = {}
    for u in np.flatnonzero(sel).tolist():
        byk.setdefault(int(M["mint"][u]), []).append(u)
    jobs = []
    for m, us in byk.items():
        a, b = spans[m]
        for i in range(0, len(us), 50): jobs.append((a, b, us[i:i + 50]))
    N = len(M); nd = len(rk)
    PN = np.full((N, nd, len(SIZES), len(FOLS), len(PL)), np.nan, np.float32)
    K = np.full((N, nd), -1, np.int16); PR = np.zeros((N, nd, len(SIZES)), np.float32); F5 = np.zeros((N, nd, len(SIZES)), bool)
    ES = np.zeros((N, nd), np.int64); EC = np.zeros((N, nd)); ET = np.zeros((N, nd, len(SIZES)))
    done = 0
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 2) as P:
        for k, out in enumerate(P.imap_unordered(work, jobs, chunksize=4)):
            for u, a_, b_, c_, d_, e_, f_, g_ in out:
                PN[u] = a_; K[u] = b_; PR[u] = c_; F5[u] = d_; ES[u] = e_; EC[u] = f_; ET[u] = g_
            done += len(out)
            if k % 2000 == 0: print(f"  {done:,}/{sel.sum():,} ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{OUT}/b5.npz", PN=PN, K=K, PR=PR, F5=F5, ES=ES, EC=EC, ET=ET, sel=sel, SIZES=np.array(SIZES), FOLS=np.array(FOLS),
             PL=np.array([str(p) for p in PL]))
    print(f"done ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
