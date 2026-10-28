#!/usr/bin/env python3
"""SELECT step 3 (read-only): y2 = what OUR entry would make on each envelope dump (INFERRED replay, the gap analyst's g10/g11 machinery:
exit analyst C's xsim.Pos + x12_wave.ev, MEASURED sell landing x7_ourexits.delays).
Events: every y1 positive (247/248 bought <= 2 slots) + a seeded 30 % sample of the rest (weight 1/0.30).
Tape: our two wallets' rows removed; haqq KEPT (a real follower) - and a NOHQ variant with haqq's rows after the dump removed
(is his own buy the follower we sell to?).
Entries (0.40 SOL, +5 % guard vs the post-dump curve):
  ps   pre-send-style, in the dump's own slot: k = outside rows ahead drawn from our MEASURED pre-send fills (g10a: 70 % k=0), 2 draws
  reg  our regular landing: dv8 rank model (k = round(q * N_w), q from the live P(q | N_w bucket)), far leaders +30 ms, 2 draws
Exits: ps WAVE_PS = RIDE(150,150,1000), T2 ; reg WAVE_REG = RIDE(150,300,2000), T5.  Followers x1.0 / x0.9.
Out: select/y2.npz: idx (into env.npz), w, ps[fol, pol] (mean over draws, unfilled = 0), psf (fill share), same for nohq and reg."""
import sys, json, time, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
SIZE = 0.40; HZ = 16; FOLS = (1.0, 0.9); FRAC = 0.30; FAR_MS = 30.0
PPS = [("RIDE", 150, 150, 1000), ("T", 2)]
PRG = [("RIDE", 150, 300, 2000), ("T", 5)]
G = {}


def work(job):
    mi, evs = job
    S_, span, cc, ours, hq, DR, DT, edges, rq = G["S"], G["span"], G["cc"], G["ours"], G["hq"], G["DR"], G["DT"], G["edges"], G["rq"]
    a, b = span[mi]; Xr = S_[a:b]
    sl = Xr["slot"].astype(np.int64); ix = Xr["idx"].astype(np.int64); us = Xr["user"].astype(np.int64); bu = Xr["buy"].astype(bool)
    so = Xr["sol"].astype(np.float64) / 1e9; tk = Xr["tok"].astype(np.float64); vs = Xr["vsol"].astype(np.float64) / 1e9
    vt = Xr["vtok"].astype(np.float64); fe = (Xr["fee_bps"].astype(np.float64) + Xr["cfee_bps"]) / 1e4; c = cc[a:b]
    o = ~np.isin(us, ours); oi = np.flatnonzero(o)
    rng = np.random.default_rng(mi)
    out = []
    for e in evs:
        jd = np.flatnonzero((sl == e["ds"]) & (ix == e["di"]) & ~bu & o)
        if not len(jd): continue
        j = int(jd[0])
        pd = int(np.searchsorted(oi, j)); fee = fe[j] if fe[j] > 0 else X.FEE; sn = SIZE / (1 + fee)
        tokd = vt[j] - vs[j] * vt[j] / (vs[j] + sn)
        # rank model draws for reg
        nw = int(np.searchsorted(sl, sl[j] + 1, side="right")) - j - 1
        bk = int(np.clip(np.searchsorted(edges, nw, side="right") - 1, 0, len(edges) - 2))
        qs = rq.get(bk, rq[max(rq)])
        kreg = [int(round(q * nw)) if nw > 0 else 0 for q in rng.choice(qs, 2)]
        kps = [int(x) for x in rng.choice(G["kpool"], 2)]
        res = {}
        for model, ks in (("ps", kps), ("reg", kreg)):
            pols = PPS if model == "ps" else PRG
            acc = np.zeros((2, len(FOLS), 2)); fills = 0
            for k in ks:
                r = min(pd + int(k), len(oi) - 1); g = oi[r]
                if model == "reg" and not e["near"]:
                    t_ = c[g] if k > 0 else c[j]
                    g2 = oi[min(int(np.searchsorted(c[oi], t_ + FAR_MS, side="right")) - 1, len(oi) - 1)]
                    g = max(g, g2)
                V0, T0 = vs[g], vt[g]; te = T0 - V0 * T0 / (V0 + sn)
                if te < tokd / 1.05: continue
                fills += 1
                hi = int(np.searchsorted(sl, sl[g] + HZ, side="right")); js = oi[(oi > g) & (oi < hi)]; c0 = c[g] + 0.01
                for vi, jj in enumerate((js, js[us[js] != hq])):
                    if model == "reg" and vi == 1: continue
                    p = dict(kind=model, V0=float(V0), T0=float(T0), sin=float(sn), cost=SIZE, fee=float(fee), off_in_slot=float(c0 - sl[g] * X.SMS),
                             dcc=(c[jj] - c0).astype(np.float64), bu=bu[jj].copy(), so=so[jj].copy(), tk=tk[jj].copy())
                    for fi, fol in enumerate(FOLS):
                        Sx = Pos(p, fol)
                        for pi, pol in enumerate(pols): acc[vi, fi, pi] += (ev(Sx, pol, DR, DT) - 1) * Sx.cost
            res[model] = (acc / len(ks), fills / len(ks))
        out.append((e["id"], res))
    return out


def main():
    t0 = time.time()
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in ("y247", "y248", "s", "i", "m")}; del Z
    y = A["y247"] | A["y248"]
    rng = np.random.default_rng(31)
    pick = y | (rng.random(len(y)) < FRAC)
    w = np.where(y, 1.0, 1 / FRAC)
    idx = np.flatnonzero(pick)
    print(f"events {len(idx):,} of {len(y):,} (pos {y.sum():,})", flush=True)
    ids, idm = L.ids_map(); ours = [idm[wl] for wl in L.WAL.values() if wl in idm]
    jobs = collections.defaultdict(list)
    lead = {}
    for u in idx.tolist():
        s = int(A["s"][u])
        if s not in lead: lead[s] = L.leader_info(s, "FRA")[2] is not False
        jobs[int(A["m"][u])].append(dict(id=u, ds=s, di=int(A["i"][u]), near=lead[s]))
    print(f"jobs on {len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mm = np.asarray(T["mint"]); sel = np.flatnonzero(np.isin(mm, np.array(sorted(jobs), np.uint32))); del mm
    cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps")
    S_ = np.zeros(len(sel), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: S_[c] = np.asarray(T[c])[sel]
    S_ = S_[np.lexsort((S_["j"], S_["idx"], S_["slot"], S_["mint"]))]
    um, st = np.unique(S_["mint"], return_index=True); en = np.append(st[1:], len(S_))
    rk = json.load(open(f"{L.D}/rank_model.json"))
    G.update(S=S_, span={int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}, cc=L.cc(S_["slot"], S_["idx"]), ours=ours, hq=idm[L.HAQQ],
             edges=np.array(rk["edges"]), rq={int(k): np.array(v) for k, v in rk["q"].items()},
             kpool=np.array(json.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g10a.json"))["k"]))
    DR, DT, _ = delays(); G.update(DR=DR, DT=DT)
    print(f"tape rows {len(S_):,} ({time.time() - t0:.0f}s)", flush=True)
    N = len(A["m"])
    PS = np.full((N, 2, len(FOLS), 2), np.nan, np.float32); PSF = np.full(N, np.nan, np.float32)
    RG = np.full((N, len(FOLS), 2), np.nan, np.float32); RGF = np.full(N, np.nan, np.float32)
    jl = sorted(jobs.items(), key=lambda kv: -len(kv[1]))
    with Pool(2) as P:
        for k, out in enumerate(P.imap_unordered(work, jl, chunksize=20)):
            for n, r in out:
                PS[n] = r["ps"][0]; PSF[n] = r["ps"][1]; RG[n] = r["reg"][0][0]; RGF[n] = r["reg"][1]
            if k % 5000 == 0: print(f"  {k:,}/{len(jl):,} ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{OUT}/y2.npz", pick=pick, w=w.astype(np.float32), PS=PS, PSF=PSF, RG=RG, RGF=RGF, FOLS=np.array(FOLS),
             PPS=np.array([str(p) for p in PPS]), PRG=np.array([str(p) for p in PRG]))
    print(f"done ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
