#!/usr/bin/env python3
"""FRONT step 1 (read-only): the paying-dump set and who lands at the front.
Universe = dv8 dump universe (dv8/uni.npz: outside non-haqq sell, drop >= 5%, sell >= 0.5 SOL, curve > 30.52, age <= 30 min),
non-mayhem, D2..D6 (10-23 23:15 -> 10-28 01:12 PKT).
Per dump (MEASURED from the tape, our wallets' rows removed for the values, kept for the listing):
  vfront   = value of a 0.40 SOL buy inserted right AFTER the dump row (state after the dump), wave exit RIDE(150,150,700) with our
             measured reactive sell delays (exit analyst x12 / x7), exact curve, gross, fol 1.0 and 0.9 (= lim l16 'ideal' wv).
  front[k] = the first 6 BUY rows after the dump (any wallet incl. ours): slot, idx, j, signer, user, sol, slot delta, chain-clock ms
             after the dump, outside rows between, and vpos = the same 0.40 SOL wave value inserted just BEFORE that buyer.
Prefilter: the exact wave value is computed only when the best curve price within dump slot + 5 is >= 1.06 x the post-dump price
(a buy needs ~+10 % to make +30 mSOL at 0.40 SOL after 2 x 1.25 % fees); others get vfront = NaN (< +30 mSOL for sure).
Out: sniper-data/haqq_dissect/front/f1.pkl"""
import sys, time, pickle, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import dv8lib as L, dv8sim as S
from xsim import Pos
from x12_wave import ev as wave_ev
from x7_ourexits import delays
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
SIZE = 0.40; WAVE = ("RIDE", 150, 150, 700); HZ = 8; NF = 6
D2 = 460541261


def main():
    t0 = time.time()
    DR, DT, _ = delays()
    ids, idm = L.ids_map()
    our = np.array([idm[w] for w in L.WAL.values() if w in idm], np.uint32)
    U = np.load(f"{L.D}/uni.npz", allow_pickle=True); M = U["M"]; mh = np.load(f"{L.D}/mayhem.npy")
    keep = (M["slot"] >= D2) & ~mh
    M = M[keep]; lcls = U["lcls"][keep]
    print(f"universe D2-D6 non-mayhem: {len(M):,} dumps ({time.time()-t0:.0f}s)", flush=True)
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    s_all = np.asarray(T["slot"])
    lo = int(np.searchsorted(s_all, D2 - 20000)) if np.all(s_all[:-1:1000] <= s_all[1::1000]) else 0
    sel = np.flatnonzero(s_all >= D2 - 20000) if lo == 0 else np.arange(lo, len(s_all))
    mids = np.unique(M["mint"])
    TT = np.asarray(T[sel]); TT = TT[np.isin(TT["mint"], mids)]
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    print(f"tape rows for those mints: {len(TT):,} ({time.time()-t0:.0f}s)", flush=True)
    isour = np.isin(TT["user"], our) | np.isin(TT["signer"], our)
    cc_all = L.cc(TT["slot"], TT["idx"])
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    rows = []
    Mo = M[np.argsort(M["mint"], kind="stable")]
    cur = None
    nval = 0
    for n_i, d in enumerate(Mo):
        mi = int(d["mint"])
        if mi != cur:
            cur = mi; a, b = span[mi]; R = TT[a:b]; ccr = cc_all[a:b]; ou = isour[a:b]
            sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
            o_idx = np.flatnonzero(~ou)   # outside rows
            Ro = R[o_idx]; slo = sl[o_idx]; ixo = ix[o_idx]; ccro = ccr[o_idx]; keyo = key[o_idx]
            vs = Ro["vsol"] / 1e9; vt = Ro["vtok"].astype(np.float64); sol = Ro["sol"] / 1e9; tk = Ro["tok"].astype(np.float64); bu = Ro["buy"].astype(bool)
            px = vs / np.maximum(vt, 1)
        ds, di = int(d["slot"]), int(d["idx"])
        # dump row in outside arrays: last row of that tx that is a sell
        jj = np.flatnonzero(keyo == ds * 100000 + di)
        jj = [j for j in jj.tolist() if not bu[j]]
        if not jj: continue
        jd = jj[-1]
        # full-array position of the dump
        jf = int(o_idx[jd])
        # ---- front listing on the full arrays (incl. ours)
        fr = []; k = jf + 1; nbetween = 0
        hi_full = int(np.searchsorted(sl, ds + HZ, side="right"))
        while k < hi_full and len(fr) < NF:
            if R["buy"][k]:
                fr.append(dict(slot=int(sl[k]), idx=int(ix[k]), j=int(R["j"][k]), signer=int(R["signer"][k]), user=int(R["user"][k]),
                               sol=float(R["sol"][k]) / 1e9, dsl=int(sl[k] - ds), ms=float(ccr[k] - ccr[jf]), nb=nbetween, ours=bool(ou[k]),
                               sigh=int(R["sigh"][k]), orow=None))
            if not ou[k]: nbetween += 1
            k += 1
        # ---- values (outside arrays)
        hi = int(np.searchsorted(slo, ds + HZ, side="right"))
        h5 = int(np.searchsorted(slo, ds + 5, side="right"))
        pmax = float(px[jd + 1:h5].max()) if h5 > jd + 1 else 0.0
        ratio = pmax / px[jd]
        vf = vf9 = np.nan

        def wave(r, cc0, fol):
            p = dict(dcc=(ccro[r:hi] - cc0).astype(np.float64), bu=bu[r:hi].copy(), so=sol[r:hi].copy(), tk=tk[r:hi].copy(),
                     V0=float(vs[r - 1]), T0=float(vt[r - 1]), sin=SIZE / (1 + S.FEE), cost=SIZE, fee=S.FEE, off_in_slot=cc0 - (cc0 // L.SMS) * L.SMS)
            P_ = Pos(p, fol)
            return (wave_ev(P_, WAVE, DR, DT) - 1) * SIZE if P_.n else (P_.v_pre - 1) * SIZE
        if ratio >= 1.06:
            nval += 1
            cc0 = float(ccro[jd]) + 0.01
            vf = wave(jd + 1, cc0, 1.0); vf9 = wave(jd + 1, cc0, 0.9)
            if vf >= 0.010:
                for f in fr:
                    if f["ours"]: continue
                    q = np.flatnonzero(keyo == f["slot"] * 100000 + f["idx"])
                    q = [x for x in q.tolist() if bu[x]]
                    if not q: continue
                    r = q[0]; f["orow"] = r
                    f["vpos"] = wave(r, float(ccro[r]) - 0.01, 1.0)
        nwin = int(np.searchsorted(slo, ds + 1, side="right")) - jd - 1
        n_same = int((bu[jd + 1:int(np.searchsorted(slo, ds, side="right"))]).sum())
        rows.append(dict(mint=mi, ds=ds, di=di, dj=int(Ro["j"][jd]), seller=int(Ro["user"][jd]), seller_sig=int(Ro["signer"][jd]), sell=float(sol[jd]),
                         drop=float(1 - px[jd] / px[jd - 1]) if jd > 0 else np.nan, vpost=float(vs[jd]), bt=int(Ro["bt"][jd]), cc=float(ccro[jd]),
                         ratio=ratio, vf=vf, vf9=vf9, nwin=nwin, n_same=n_same, front=fr, dsigh=int(Ro["sigh"][jd]),
                         hq=bool(d["hq"]), age=int(d["age"])))
        if n_i % 50000 == 0: print(f"  {n_i:,}/{len(Mo):,} dumps, {nval:,} valued ({time.time()-t0:.0f}s)", flush=True)
    pickle.dump(rows, open(f"{OUT}/f1.pkl", "wb"))
    v = np.array([r["vf"] for r in rows])
    print(f"done {len(rows):,} dumps; valued {nval:,}; vfront>=30 mSOL: {(v >= 0.030).sum():,} ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
