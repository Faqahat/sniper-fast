#!/usr/bin/env python3
"""GAP step 11 (read-only): is the pre-send-style entry on CREATION-SLOT-BUYER dumps positive WITHOUT haqq's selection?
Universe (causal, no haqq info): every DV8 candidate (outside sell >= 0.5 SOL, drop >= 5 %, curve > 30.5, age <= 30 min, non-mayhem,
usable hours) whose seller is the creator or bought in the creation slot (uni features d_dev / d_bund), days D0-D5; a 30 % random
sample per day (seeded). Per event, from the tape (our wallets removed, haqq kept): the seller's token balance before the dump (% of
supply) and slots since the seller's first buy (= how long a pre-arm on that wallet would have been live, lower bound), whether haqq
bought within 2 slots (uni 'hq').
Entries as g10: ps (MEASURED pre-send positions, 3 draws; x0.45 fill applied in the report) and reg (4 rank draws). Exits via C's
code (xsim.Pos + x12_wave.ev, MEASURED sell landing). Followers 1.0 / 0.9 / 0.8.
Out: gap/g11_res.pkl"""
import pickle, sys, json, time, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
SIZE = 0.40; HZ = 16; FOLS = (1.0, 0.9, 0.8); FRAC = 0.30
PL = [("T", 2), ("T", 5), ("MS", 200), ("RIDE", 150, 150, 1000), ("RIDE", 150, 300, 2000), ("RIDE", 200, 300, 2000)]
G = {}


def work(job):
    mi, evs = job
    S_, span, cc, ours, DR, DT = G["S"], G["span"], G["cc"], G["ours"], G["DR"], G["DT"]
    a, b = span[mi]; Xr = S_[a:b]
    sl = Xr["slot"].astype(np.int64); ix = Xr["idx"].astype(np.int64); us = Xr["user"].astype(np.int64); bu = Xr["buy"].astype(bool)
    so = Xr["sol"].astype(np.float64) / 1e9; tk = Xr["tok"].astype(np.float64); vs = Xr["vsol"].astype(np.float64) / 1e9
    vt = Xr["vtok"].astype(np.float64); fe = (Xr["fee_bps"].astype(np.float64) + Xr["cfee_bps"]) / 1e4; c = cc[a:b]
    o = ~np.isin(us, ours); oi = np.flatnonzero(o)
    stok = np.where(bu, tk, -tk)
    out = []
    for e in evs:
        jd = np.flatnonzero((sl == e["ds"]) & (ix == e["di"]) & ~bu & o)
        if not len(jd): continue
        j = int(jd[0]); seller = us[j]
        mine = us[:j] == seller
        bal = float(stok[:j][mine].sum()) / 1e13
        fb = np.flatnonzero(mine & bu[:j]); arm_slots = int(sl[j] - sl[fb[0]]) if len(fb) else -1
        pd = int(np.searchsorted(oi, j)); fee = fe[j] if fe[j] > 0 else X.FEE; sn = SIZE / (1 + fee)
        tokd = vt[j] - vs[j] * vt[j] / (vs[j] + sn)
        res = []
        for model, k in [("reg", kk) for kk in e["kreg"]] + [("ps", kk) for kk in e["kps"]]:
            r = min(pd + int(k), len(oi) - 1); g = oi[r]
            V0, T0 = vs[g], vt[g]; te = T0 - V0 * T0 / (V0 + sn)
            if te < tokd / 1.05: res.append((model, False, None)); continue
            hi = int(np.searchsorted(sl, sl[g] + HZ, side="right")); js = oi[(oi > g) & (oi < hi)]; c0 = c[g] + 0.01
            p = dict(kind=model, V0=float(V0), T0=float(T0), sin=float(sn), cost=SIZE, fee=float(fee), off_in_slot=float(c0 - sl[g] * X.SMS),
                     dcc=(c[js] - c0).astype(np.float64), bu=bu[js].copy(), so=so[js].copy(), tk=tk[js].copy())
            pols = PL if model == "ps" else [PL[1], PL[4]]
            fols = FOLS if model == "ps" else FOLS[:2]
            pn = np.full((len(FOLS), len(PL)), np.nan)
            for fi, fol in enumerate(fols):
                Sx = Pos(p, fol)
                for pol in pols: pn[fi, PL.index(pol)] = (ev(Sx, pol, DR, DT) - 1) * Sx.cost
            res.append((model, True, pn))
        out.append((e["id"], dict(bal=bal, arm=arm_slots, res=res)))
    return out


def main():
    t0 = time.time()
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; Xf = U["X"]; R = U["R"]; names = list(U["names"])
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    cand = np.flatnonzero(usable & ((Xf[:, 9] > 0) | (Xf[:, 10] > 0)) & (day >= 0) & (day <= 5))
    rng = np.random.default_rng(21)
    cand = cand[rng.random(len(cand)) < FRAC]
    kpool = np.array(json.load(open(f"{OUT}/g10a.json"))["k"])
    meta = {}; jobs = collections.defaultdict(list)
    for u in cand.tolist():
        meta[u] = dict(day=int(day[u]), dev=bool(Xf[u, 9] > 0), hq=bool(M["hq"][u]), near=bool(U["near"][u]), sell=float(Xf[u, 1]), drop=float(Xf[u, 0]))
        jobs[int(M["mint"][u])].append(dict(id=u, ds=int(M["slot"][u]), di=int(M["idx"][u]), kreg=[int(R[u, c] - M["row"][u] - 1) for c in rk],
                                            kps=[int(x) for x in rng.choice(kpool, 3)]))
    print(f"sample {len(cand):,} events on {len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    ids, idm = L.ids_map(); ours = [idm[w] for w in L.WAL.values() if w in idm]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mm = np.asarray(T["mint"]); sel = np.flatnonzero(np.isin(mm, np.array(sorted(jobs), np.uint32))); del mm
    cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps")
    S_ = np.zeros(len(sel), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: S_[c] = np.asarray(T[c])[sel]
    S_ = S_[np.lexsort((S_["j"], S_["idx"], S_["slot"], S_["mint"]))]
    um, st = np.unique(S_["mint"], return_index=True); en = np.append(st[1:], len(S_))
    G.update(S=S_, span={int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}, cc=L.cc(S_["slot"], S_["idx"]), ours=ours)
    DR, DT, _ = delays(); G.update(DR=DR, DT=DT)
    print(f"tape rows {len(S_):,} ({time.time() - t0:.0f}s)", flush=True)
    res = {}
    jl = sorted(jobs.items(), key=lambda kv: -len(kv[1]))
    with Pool(3) as P:
        for k, out in enumerate(P.imap_unordered(work, jl, chunksize=50)):
            for n, r in out: res[n] = r
            if k % 5000 == 0: print(f"  {k:,}/{len(jl):,} ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(meta=meta, res=res, PL=PL, FOLS=FOLS, frac=FRAC), open(f"{OUT}/g11_res.pkl", "wb"))
    print(f"done {len(res):,} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
