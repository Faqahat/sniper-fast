#!/usr/bin/env python3
"""BOTS step 4 (read-only): THE TEST. Exact curve replay (analyst C's xsim.Pos = dv8sim exact semantics; C's MEASURED sell-landing delays)
of
 (A) every bot-247 / bot-248 dump lot inside the dv8 universe (usable hours, non-mayhem), with the bot REPLACED by us: his buy row and his
     code-matched sells of that lot are removed from the tape (our two wallets' rows removed too; other haqq bots stay = real followers).
     Entries:  his   = our buy lands exactly where his landed (validation: his exit must reproduce his realized lot)
               reg0-3 = our REGULAR landing, the 4 contention-aware rank draws of dv8 uni.npz (k outside trades ahead, far leaders +30 ms),
                        mapped to the same physical chain point (if his buy was ahead of us it is simply gone)
     Size = the bot's size (247 0.40, 248 0.30).
 (B) our 1,544 live regular fires (calibration set): entry real = our ACTUAL landed position (MEASURED, incl. failed fires: the tx landed),
     rank0-7 = 8 rank-model draws (dv8 rank_model.json, k = round(q x N_w)); size 0.40.
Per entry: k ahead, price paid vs post-dump (pr = post-dump tokens / our tokens), fill under the +5 % guard (no-limit always fills).
Exits (decided causally; xsim MEASURED delays): HIS (lots: sell at the bot's own code-matched sell times, same fractions), T5 (our current
regular timer), WAVE_REG = RIDE(150 ms, 300 ms gap, 2 s cap), WAVE_PS = RIDE(150, 150, 1 s), MS200, MS4000 (sell ~4 s after the fill).
Followers: outside buy SOL after our entry x1.0 / 0.9 / 0.8.  Curve P&L in SOL (tx costs added in b6).
Out: bots/b4_res.pkl"""
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
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
FOLS = (1.0, 0.9, 0.8)
PL = [("HIS",), ("T", 5), ("RIDE", 150, 300, 2000), ("RIDE", 150, 150, 1000), ("MS", 200), ("MS", 1000), ("MS", 2000), ("MS", 4000), ("RIDE", 424, 1000, 10000)]
KEEP = len(sys.argv) > 1 and sys.argv[1] == "keep"     # variant: his lot stays in the tape (he is then a competitor right behind / ahead of us)
NB = (0, 1, 2, 3, 5, 8, 13, 10 ** 6)
_G = {}


def init():
    _G["tape"] = X.tape(); _G["D"] = delays()
    W = _G["tape"][1]["who"]; _G["ours"] = [W["FRA"], W["AMS"]]; _G["haqq"] = W["haqq"]
    _G["codes"] = pickle.load(open(f"{OUT}/hcodes.pkl", "rb"))
    S = np.load(f"{OUT}/b4_suptape.npy"); _G["sup"] = S
    um, st = np.unique(S["mint"], return_index=True); en = np.append(st[1:], len(S))
    _G["supspan"] = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    _G["supinfo"] = pickle.load(open(f"{OUT}/b4_supinfo.pkl", "rb"))
    rk = json.load(open(f"{L.D}/rank_model.json")); _G["rq"] = {int(k): np.array(v) for k, v in rk["q"].items()}


class SupMint:
    """same fields as xlib.Mint for a mint missing from the exit tape (only our failed fires)"""
    def __init__(self, m):
        a, b = _G["supspan"][m]; Xr = _G["sup"][a:b]; self.n = b - a
        self.sl = Xr["slot"].astype(np.int64); self.ix = Xr["idx"].astype(np.int64); self.us = Xr["user"].astype(np.int64)
        self.bu = Xr["buy"].astype(bool); self.so = Xr["sol"].astype(np.float64) / 1e9; self.tk = Xr["tok"].astype(np.float64)
        self.vs = Xr["vsol"].astype(np.float64) / 1e9; self.vt = Xr["vtok"].astype(np.float64); self.bt = Xr["bt"].astype(np.int64)
        self.fee = (Xr["fee_bps"].astype(np.float64) + Xr["cfee_bps"].astype(np.float64)) / 1e4
        self.cc = L.cc(self.sl, self.ix)


def mint(m):
    if m in _G["tape"][2]: return X.Mint(m)
    return SupMint(m)


def make_pos(Mn, oi, g, size, fee, horizon_slots):
    sn = size / (1 + fee)
    V0, T0 = Mn.vs[g], Mn.vt[g]
    hi = int(np.searchsorted(Mn.sl, Mn.sl[g] + horizon_slots, side="right"))
    js = oi[(oi > g) & (oi < hi)]
    c0 = Mn.cc[g] + 0.01
    p = dict(kind="reg", V0=float(V0), T0=float(T0), sin=float(sn), cost=size, fee=float(fee), off_in_slot=float(c0 - Mn.sl[g] * X.SMS),
             dcc=(Mn.cc[js] - c0).astype(np.float64), bu=Mn.bu[js].copy(), so=Mn.so[js].copy(), tk=Mn.tk[js].copy())
    return p, c0


def eval_all(p, c0, plan, DR, DT):
    """curve P&L (SOL) [fol, policy]"""
    pn = np.full((len(FOLS), len(PL)), np.nan)
    for fi, fol in enumerate(FOLS):
        S = Pos(p, fol)
        for a, pol in enumerate(PL):
            if pol[0] == "HIS":
                if plan is None: continue
                v = S.partial_exact([(t - c0, fr) for t, fr in plan]) if S.n else S.v_pre
            else:
                v = ev(S, pol, DR, DT)
            pn[fi, a] = (v - 1) * S.cost
    return pn


def work(job):
    m, evs = job
    DR, DT, _ = _G["D"]
    Mn = mint(m)
    base_rm = np.isin(Mn.us, _G["ours"])
    out = []
    for e in evs:
        jd = np.flatnonzero((Mn.sl == e["ds"]) & (Mn.ix == e["di"]) & ~Mn.bu)
        if not len(jd): out.append((e["id"], None)); continue
        jd = int(jd[0])
        rm = base_rm.copy(); plan = None
        if e["kind"] == "lot":
            hb = np.flatnonzero((Mn.sl == e["slot"]) & (Mn.ix == e["idx"]) & Mn.bu & (Mn.us == _G["haqq"]))
            if not len(hb): out.append((e["id"], None)); continue
            hb = int(hb[0]); rm[hb] = not KEEP
            hs = np.flatnonzero((Mn.us == _G["haqq"]) & ~Mn.bu & (Mn.cc > Mn.cc[hb]) & (Mn.cc <= (e["close_cc"] or 0) + 1.0))
            hs = [j for j in hs.tolist() if _G["codes"].get((int(Mn.sl[j]), int(Mn.ix[j]))) == e["code"]]
            if hs:
                tot = Mn.tk[hs].sum()
                plan = [(float(Mn.cc[j]), float(Mn.tk[j] / tot)) for j in hs]
                rm[hs] = not KEEP
        oi = np.flatnonzero(~rm)
        pd = int(np.searchsorted(oi, jd))           # oi[pd] == jd
        fee = Mn.fee[jd] if Mn.fee[jd] > 0 else X.FEE
        size = e["size"]; sn = size / (1 + fee)
        vd, td = Mn.vs[jd], Mn.vt[jd]; tokd = td - vd * td / (vd + sn)
        # entries -> g = last kept row before our buy
        ents = []
        if e["kind"] == "lot":
            if e.get("our_us") is not None:     # b16: our REAL landed position on this dump (live fire), his lot removed
                ub = np.searchsorted(Mn.sl * 100000 + Mn.ix, e["our_us"][0] * 100000 + e["our_us"][1])
                ents.append(("ours_real", int(oi[np.searchsorted(oi, ub) - 1])))
            ents.append(("his", int(oi[np.searchsorted(oi, hb) - 1])))
            full = np.flatnonzero(~base_rm)            # tape with haqq, ours removed = the uni tape
            pf = int(np.searchsorted(full, jd))
            for d, k in enumerate(e["kreg"]):
                gf = full[min(pf + k, len(full) - 1)]
                ents.append((f"reg{d}", int(oi[np.searchsorted(oi, gf, side="right") - 1])))
        else:
            ub = np.searchsorted(Mn.sl * 100000 + Mn.ix, e["us"][0] * 100000 + e["us"][1])     # first row at/after our landed tx
            ents.append(("real", int(oi[np.searchsorted(oi, ub) - 1])))
            nw = int(np.searchsorted(Mn.sl[oi], e["ds"] + 1, side="right")) - pd - 1
            b = int(np.searchsorted(NB, nw, side="right") - 1); qs = _G["rq"].get(b, _G["rq"][max(_G["rq"])])
            rng = np.random.default_rng(int(e["id"]) * 7 + 1)
            for d in range(8):
                q = qs[rng.integers(0, len(qs))]; k = int(round(q * nw)) if nw > 0 else int(q)
                ents.append((f"rank{d}", int(oi[min(pd + k, len(oi) - 1)])))
        hz = 55
        if plan: hz = int(min(1500, max(55, int(plan[-1][0] // X.SMS) - int(Mn.sl[jd]) + 4)))
        res = []
        for nm, g in ents:
            g = max(g, jd)
            k = int(np.searchsorted(oi, g) - pd)        # outside rows ahead of us after the dump
            V0, T0 = Mn.vs[g], Mn.vt[g]; te = T0 - V0 * T0 / (V0 + sn)
            p, c0 = make_pos(Mn, oi, g, size, fee, hz)
            pn = eval_all(p, c0, plan, DR, DT)
            res.append(dict(m=nm, k=k, pr=float(tokd / max(te, 1)), fill5=bool(te >= tokd / 1.05), slot=int(Mn.sl[g]), cc=float(c0), tok=float(te), pn=pn))
        out.append((e["id"], res))
    return out


def prep():
    """events + supplementary tape for fire mints absent from the exit tape; haqq row codes"""
    t0 = time.time()
    ids, idm = L.ids_map()
    C = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/pos/codes.pkl", "rb"))
    pickle.dump({k: v[0] for k, v in C.items() if k[0] != "F"}, open(f"{OUT}/hcodes.pkl", "wb"))
    R, MI, span, _ = X.tape()
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    miss = sorted({idm[f["mint"]] for f in F if f["mint"] in idm and idm[f["mint"]] not in span})
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    sel = np.isin(np.asarray(T["mint"]), np.array(miss, np.uint32))
    cols = R.dtype.names
    S = np.zeros(int(sel.sum()), dtype=R.dtype)
    for c in cols: S[c] = np.asarray(T[c])[sel]
    S = S[np.lexsort((S["j"], S["idx"], S["slot"], S["mint"]))]
    np.save(f"{OUT}/b4_suptape.npy", S); pickle.dump({}, open(f"{OUT}/b4_supinfo.pkl", "wb"))
    print(f"supplementary tape: {len(miss)} mints, {len(S):,} rows ({time.time() - t0:.0f}s)", flush=True)
    rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; RR = U["R"]; names = list(U["names"])
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    may = np.load(f"{L.D}/mayhem.npy")
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    evs = collections.defaultdict(list); meta = {}
    n = 0
    for r in rows:
        if r["code"] not in (247, 248) or r["u"] is None or not r["dump"] or r["gap"]: continue
        u = r["u"]
        if may[u]: continue
        hs = (int(M["bt"][u]) + 18000) // 3600 * 3600 - 18000
        if hs not in good: continue
        kreg = [int(RR[u, c] - M["row"][u] - 1) for c in rk]
        e = dict(id=n, kind="lot", ds=int(M["slot"][u]), di=int(M["idx"][u]), slot=r["slot"], idx=r["idx"], close_cc=r["close_cc"], code=r["code"],
                 size=round(r["size"], 2), kreg=kreg)
        evs[r["mi"]].append(e)
        meta[n] = dict(kind="lot", code=r["code"], u=int(u), li=r["li"], day=r["day"], net=r["net"], gross=r["gross"], size=r["size"], hold=r["hold"],
                       d_type=r["d_type"], near=bool(U["near"][u]), mint=r["mint"], dslot=int(M["slot"][u]), didx=int(M["idx"][u]), bt=int(M["bt"][u]),
                       hslot=r["slot"], hidx=r["idx"])
        n += 1
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in idm: continue
        e = dict(id=n, kind="fire", ds=f["ds"], di=f["di"], us=f["us"], size=0.40)
        evs[idm[f["mint"]]].append(e)
        meta[n] = dict(kind="fire", run=f["run"], srv=f["srv"], t=f["t"], out=f["out"], realized=f["realized"], spend=f["spend"], day=L.day_of(f["t"]),
                       m2=f.get("m2"), mint=f["mint"])
        n += 1
    return evs, meta


def main():
    t0 = time.time()
    evs, meta = prep()
    jobs = sorted(evs.items(), key=lambda kv: -len(kv[1]))
    print(f"events {len(meta):,} on {len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    res = {}
    with Pool(2, initializer=init) as P:
        for k, out in enumerate(P.imap_unordered(work, jobs, chunksize=10)):
            for i, r in out: res[i] = r
            if k % 1000 == 0: print(f"  {k:,}/{len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(meta=meta, res=res, PL=PL, FOLS=FOLS), open(f"{OUT}/b4_res{'_keep' if KEEP else ''}.pkl", "wb"))
    print(f"done ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
