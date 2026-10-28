#!/usr/bin/env python3
"""FOLLOW step 2 (read-only): the value of an armed pre-send attempt at every CROSSING that some large-holder episode window can see.
Relevant crossings = inside [episode start, the whale's next sell + 30 ms] (open episodes: start + 400 slots) of an episode on a
non-mayhem SOL-quote token with a create record, in a usable tape hour, days D0..D6.
Landing (INFERRED from MEASURED live fills, A's p8c method): k = outside trades between the crossing trade and our buy,
k = round(q x N_w), q drawn from our 1,144 live pre-send fills in the same N_w bucket (N_w = outside trades after the crossing to the
end of slot +1); 4 draws per crossing. FILL iff the price after those k trades is still <= 0.88 x the reference (the engine's
min-out: latest price x (1 - 0.12) on the same curve; reference = post-trade price of the last trade >= 50 ms before the crossing)
and the curve is < 100 SOL. A failed draw = no fill at THIS crossing (the attempts go on; a later crossing can fill).
Exit (C's code, MEASURED sell landing): WAVE = RIDE(150,150,1000) (pre-send wave exit), T2 = 2-slot timer, WAVE2 = RIDE(150,300,2000).
Followers x1.0 / 0.9 / 0.8 (C's Pos fol). 0.40 SOL. Value = curve P&L in SOL, gross of tx costs.
Also per crossing: haqq bought within 2 slots after it (MEASURED, aux label), the seller, whether the seller held >= 6 % before.
Out: cross_val.npz"""
import sys, time, pickle, json, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/follow"
SIZE = 0.40; HZ = 16; FOLS = (1.0, 0.9, 0.8); ND = 4; SMS = 212.0; FEE = 0.0125; OPEN_CAP = 400
PL = [("RIDE", 150, 150, 1000), ("T", 2), ("RIDE", 150, 300, 2000)]
EDG = (0, 1, 2, 3, 5, 8, 13, 10 ** 6)
G = {}


def bk(n): return int(np.searchsorted(EDG, n, side="right") - 1)


def landing_model(R, mst_en):
    """q = k / N_w per N_w bucket from our live pre-send fills (dv8 live_presend.pkl), N_w from this tape"""
    ids, idm = L.ids_map()
    lp = pickle.load(open(f"{L.D}/live_presend.pkl", "rb"))
    st, en = mst_en
    q_by = collections.defaultdict(list)
    for x in lp:
        if x.get("res") != "ok" or x.get("n_between") is None or x.get("dslot") is None or x["mint"] not in idm: continue
        m = idm[x["mint"]]
        if m not in st: continue
        a, b = st[m], en[m]
        sl = R["slot"][a:b]; ix = R["idx"][a:b]
        dj = np.flatnonzero((sl == x["dslot"]) & (ix == x["didx"]))
        if not len(dj): continue
        d = int(dj[-1]); hi = int(np.searchsorted(sl, x["dslot"] + 1, side="right"))
        nw = hi - d - 1
        q_by[bk(nw)].append(min(x["n_between"], nw) / max(nw, 1) if nw > 0 else 0.0)
    return {k: np.array(v) for k, v in q_by.items()}


def work(chunk):
    R = G["R"]; X = G["X"]; DR, DT = G["DR"], G["DT"]; q_by = G["q"]; hq = G["haqq"]
    px, ref, cc, bb = X["px"], X["ref"], X["cc"], X["bb"]
    rng = np.random.default_rng(int(chunk[0][0]) % 100003)
    out = []
    for x, nw, mend in chunk:
        sl0 = int(R["slot"][x])
        qs = q_by[bk(nw)] if bk(nw) in q_by else q_by[max(q_by)]
        lim = 0.88 * ref[x]
        f = (R["fee_bps"][x] + R["cfee_bps"][x]) / 1e4
        fee = float(f) if f > 0 else FEE
        sn = SIZE / (1 + fee)
        # haqq bought within 2 slots after the crossing
        hi2 = x + 1 + int(np.searchsorted(R["slot"][x + 1:mend], sl0 + 2, side="right"))
        hqb = bool(np.any((R["user"][x + 1:hi2] == hq) & (R["buy"][x + 1:hi2] == 1)))
        draws = []
        for qd in rng.choice(qs, ND):
            k = int(round(qd * nw)); g = x + k
            if g >= mend: g = mend - 1
            if not (px[g] <= lim) or R["vsol"][g] >= 100e9: draws.append((k, False, None)); continue
            sg = int(R["slot"][g])
            hi = g + 1 + int(np.searchsorted(R["slot"][g + 1:mend], sg + HZ, side="right"))
            js = np.arange(g + 1, hi)
            c0 = cc[g] + 0.01
            p = dict(kind="ps", V0=float(R["vsol"][g]) / 1e9, T0=float(R["vtok"][g]), sin=float(sn), cost=SIZE, fee=fee, off_in_slot=float(c0 - sg * SMS),
                     dcc=(cc[js] - c0).astype(np.float64), bu=R["buy"][js].astype(bool), so=R["sol"][js].astype(np.float64) / 1e9, tk=R["tok"][js].astype(np.float64))
            pn = np.zeros((len(FOLS), len(PL)))
            for fi, fol in enumerate(FOLS):
                S = Pos(p, fol)
                for a, pol in enumerate(PL): pn[fi, a] = (ev(S, pol, DR, DT) - 1) * S.cost
            # entry price / tokens (for the decision log)
            V0 = p["V0"]; T0 = p["T0"]; tok = T0 - V0 * T0 / (V0 + sn)
            draws.append((k, True, (pn, int(g), float(V0 / T0 * 1e6), float(tok))))
        out.append((x, hqb, draws))
    return out


def main():
    t0 = time.time()
    R = np.load(f"{OUT}/tape.npy"); X = dict(np.load(f"{OUT}/rowx.npz"))
    MI = pickle.load(open(f"{OUT}/mints.pkl", "rb")); info = MI["info"]
    st = {int(m): int(a) for m, a in zip(MI["um"], MI["st"])}; en = {int(m): int(b) for m, b in zip(MI["um"], MI["en"])}
    E = dict(np.load(f"{OUT}/episodes.npz")); C = dict(np.load(f"{OUT}/cross.npz"))
    hrs = json.load(open(f"{L.D}/hours.json")); good = np.array(sorted({r["h"] for r in hrs["rows"] if r["usable"]}))
    bt = R["bt"].astype(np.int64)
    okm = np.zeros(int(MI["um"].max()) + 1, bool)
    for m, c in info.items(): okm[m] = (c["cs"] is not None) and not c["mayhem"] and c["quote_ok"]
    r0 = E["r0"]; r1 = E["r1"]; em = E["mint"]
    hstart = (bt[r0] + 18000) // 3600 * 3600 - 18000
    eok = okm[em] & np.isin(hstart, good) & (((bt[r0] - L.DAY0) // 86400) <= 6)
    print(f"episodes {len(r0):,}, usable {int(eok.sum()):,} ({time.time() - t0:.0f}s)", flush=True)
    # relevant crossings: per mint, union of episode windows
    cc = X["cc"]
    cend = np.where(r1 >= 0, cc[np.clip(r1, 0, None)] + 30.0, cc[r0] + OPEN_CAP * SMS)
    win = collections.defaultdict(list)
    for a, b, m in zip(cc[r0][eok].tolist(), cend[eok].tolist(), em[eok].tolist()): win[m].append((a, b))
    cr = C["row"]; nw = C["nw"]; cm = R["mint"][cr].astype(np.int64)
    rel = np.zeros(len(cr), bool)
    order = np.argsort(cm, kind="stable")
    for i in order.tolist():
        w = win.get(int(cm[i]))
        if not w: continue
        c = cc[cr[i]]
        for a, b in w:
            if a < c <= b: rel[i] = True; break
    print(f"crossings {len(cr):,}, relevant {int(rel.sum()):,} ({time.time() - t0:.0f}s)", flush=True)
    q_by = landing_model(R, (st, en))
    print("landing model buckets: " + ", ".join(f"{EDG[k]}+: n={len(v)} mean q {v.mean():.2f}" for k, v in sorted(q_by.items())), flush=True)
    DR, DT, _ = delays()
    G.update(R=R, X=X, DR=DR, DT=DT, q=q_by, haqq=MI["haqq"])
    jobs = [(int(cr[i]), int(nw[i]), en[int(cm[i])]) for i in np.flatnonzero(rel)]
    chunks = [jobs[i:i + 400] for i in range(0, len(jobs), 400)]
    res = []
    with Pool(3) as P:
        for k, o in enumerate(P.imap_unordered(work, chunks)):
            res.extend(o)
            if k % 50 == 0: print(f"  {k}/{len(chunks)} ({time.time() - t0:.0f}s)", flush=True)
    res.sort(key=lambda z: z[0])
    n = len(res)
    row = np.array([z[0] for z in res], np.int64); hqb = np.array([z[1] for z in res])
    fill = np.zeros((n, ND), bool); kk = np.zeros((n, ND), np.int32); val = np.zeros((n, ND, len(FOLS), len(PL)))
    grow = np.full((n, ND), -1, np.int64); epx = np.zeros((n, ND)); etok = np.zeros((n, ND))
    for i, (_, _, d) in enumerate(res):
        for j, (k, f, v) in enumerate(d):
            kk[i, j] = k; fill[i, j] = f
            if f: val[i, j] = v[0]; grow[i, j] = v[1]; epx[i, j] = v[2]; etok[i, j] = v[3]
    np.savez(f"{OUT}/cross_val.npz", row=row, hqb=hqb, fill=fill, k=kk, val=val, grow=grow, epx=epx, etok=etok, PL=np.array([str(p) for p in PL]), FOLS=np.array(FOLS))
    print(f"done {n:,}: fill share {fill.mean():.2f}; WAVE fol1 mean per fill {1000 * val[..., 0, 0][fill].mean():+.2f} mSOL ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
