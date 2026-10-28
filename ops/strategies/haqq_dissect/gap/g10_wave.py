#!/usr/bin/env python3
"""GAP step 10 (read-only): section-5 capture replay redone with analyst C's WAVE exit (C's code imported: xsim.Pos, x12_wave.ev,
x7_ourexits.delays = our MEASURED sell landing: reactive median ~59 ms; timer sells per kind).
Events = his dump events (single-sell drop >= 5 %; DIP / ADD-on-dump within 2 slots, DIP_LATE within 5 slots) in usable tape hours,
non-mayhem, matched to the DV8 universe (for the validated rank-landing draws). Event bucket = bucket of his first lot on it;
his net = all his lots on it (MEASURED).
Entry models (0.40 SOL, +5 % guard vs the post-dump curve, our two wallets' rows removed, haqq kept):
  reg  our regular landing: k outside trades ahead = the 4 rank-model draws of dv8/uni.npz (contention-aware, far +30 ms)
  ps   pre-send-style landing (in the dump's own slot): k drawn from our MEASURED pre-send fills (g10a: 70 % k=0, p90 2, median 28 ms),
       3 draws; P(fill | armed and the whale sells) = 0.45 MEASURED (g10a) applied as a factor; arming cost not included (break-even shown)
Exits (C): T5 (our current regular timer), T2, MS t, RIDE(t1, S, tmax) = from t1 ms after our fill hold while an outside buy landed in
  the last S ms, sell at the first S-ms gap, cap tmax. WAVE_PS = RIDE(150,150,1000), WAVE_REG = RIDE(150,300,2000).
Followers: every outside buy after our entry scaled x1.0 / 0.9 / 0.8 (C's Pos fol).
Out: gap/g10_res.pkl (per event x model-draw x fol x policy curve P&L), consumed by g10b."""
import pickle, sys, collections, json, time
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
SIZE = 0.40; HZ = 16; FOLS = (1.0, 0.9, 0.8); NPS = 3
PL = [("T", 5), ("T", 2), ("MS", 100), ("MS", 200), ("MS", 300), ("MS", 400)]
PL += [("RIDE", t1, s, t) for t1 in (150, 200) for s in (100, 150, 300) for t in (400, 700, 1000, 2000)]
_G = {}


NOHQ = len(sys.argv) > 1 and sys.argv[1] == "nohaqq"      # variant: haqq's own rows removed too (is HE the follower we sell to?)


def init():
    _G["tape"] = X.tape(); _G["D"] = delays()
    _G["ours"] = [_G["tape"][1]["who"]["FRA"], _G["tape"][1]["who"]["AMS"]] + ([_G["tape"][1]["who"]["haqq"]] if NOHQ else [])


def work(args):
    m, evs = args
    DR, DT, _ = _G["D"]; ours = _G["ours"]
    M = X.Mint(m)
    o = ~np.isin(M.us, ours); oi = np.flatnonzero(o)
    out = []
    for e in evs:
        jd = np.flatnonzero((M.sl == e["ds"]) & (M.ix == e["di"]) & ~M.bu & o)
        if not len(jd): out.append((e["id"], None)); continue
        pd = int(np.searchsorted(oi, int(jd[0])))
        fee = M.fee[jd[0]] if M.fee[jd[0]] > 0 else X.FEE
        sn = SIZE / (1 + fee)
        vd, td = M.vs[oi[pd]], M.vt[oi[pd]]; tokd = td - vd * td / (vd + sn)
        res = []
        for model, k in [("reg", kk) for kk in e["kreg"]] + [("ps", kk) for kk in e["kps"]]:
            r = pd + int(k)
            if r >= len(oi): r = len(oi) - 1
            g = oi[r]                                   # we land right after outside row g
            V0, T0 = M.vs[g], M.vt[g]; te = T0 - V0 * T0 / (V0 + sn)
            fill = te >= tokd / 1.05
            if not fill: res.append((model, False, None)); continue
            hi = int(np.searchsorted(M.sl, M.sl[g] + HZ, side="right"))
            js = oi[(oi > g) & (oi < hi)]
            c0 = M.cc[g] + 0.01
            p = dict(kind=model, V0=float(V0), T0=float(T0), sin=float(sn), cost=SIZE, fee=float(fee), off_in_slot=float(c0 - M.sl[g] * X.SMS),
                     dcc=(M.cc[js] - c0).astype(np.float64), bu=M.bu[js].copy(), so=M.so[js].copy(), tk=M.tk[js].copy())
            pn = np.zeros((len(FOLS), len(PL)))
            for fi, fol in enumerate(FOLS):
                S = Pos(p, fol)
                for a, pol in enumerate(PL): pn[fi, a] = (ev(S, pol, DR, DT) - 1) * S.cost
            res.append((model, True, pn))
        out.append((e["id"], res))
    return out


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; R = U["R"]; names = list(U["names"])
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]
    may = np.load(f"{L.D}/mayhem.npy")
    key = {(int(m), int(s), int(i)): k for k, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    ids, idm = L.ids_map()
    G = json.load(open(f"{OUT}/g10a.json")); kps_pool = np.array(G["k"])
    rng = np.random.default_rng(11)
    E = {}
    for i, r in enumerate(rows):
        b = r["b"]
        if r["bucket"] == "NOCOV" or r["type"] == "PROBE" or b.get("d_slot") is None or b["d_drop"] < 0.05: continue
        lim = 5 if r["type"] == "DIP_LATE" else 2
        if b["d_slots"] > lim: continue
        kk = (idm.get(b["mint"]), b["d_slot"], b["d_i"])
        if kk not in E: E[kk] = dict(lots=[], first=None)
        E[kk]["lots"].append(i)
    evs = collections.defaultdict(list); meta = {}; nmiss = 0
    for n, (kk, v) in enumerate(E.items()):
        u = key.get(kk)
        if u is None or may[u]: nmiss += 1; continue
        lots = sorted(v["lots"], key=lambda i: rows[i]["b"]["bt"]); f = rows[lots[0]]
        bk = ("e" if f["bucket"] == "e" else "f" if f["bucket"] == "f" else "a" if f["bucket"] == "a" else
              ("b:" + f["reason"]) if f["bucket"] == "b" else ("c:" + f["reason"]))
        meta[n] = dict(day=f["day"], bucket=bk, his=sum(rows[i]["net"] for i in lots), nlots=len(lots), dtype=f["b"]["d_type"],
                       bal=f["b"].get("d_bal_pct") or 0.0, mint=f["b"]["mint"], near=bool(U["near"][u]), cc=float(M["cc"][u]), ufill=[bool(U["FILL"][u, c]) for c in rk])
        kreg = [int(R[u, c] - M["row"][u] - 1) for c in rk]
        evs[int(kk[0])].append(dict(id=n, ds=kk[1], di=kk[2], kreg=kreg, kps=[int(x) for x in rng.choice(kps_pool, NPS)]))
    # map tape mint ids (X tape uses dv8 ids) -> same ids
    jobs = sorted(evs.items(), key=lambda kv: -len(kv[1]))
    print(f"events {len(meta):,} (unmatched/mayhem {nmiss:,}) on {len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    res = {}
    with Pool(3, initializer=init) as P:
        for k, out in enumerate(P.imap_unordered(work, jobs, chunksize=20)):
            for n, r in out: res[n] = r
            if k % 2000 == 0: print(f"  {k:,}/{len(jobs):,} mints ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(meta=meta, res=res, PL=PL, FOLS=FOLS), open(f"{OUT}/g10_res{'_nohaqq' if NOHQ else ''}.pkl", "wb"))
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
