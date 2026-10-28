#!/usr/bin/env python3
"""FOLLOW step 3 (read-only): CAUSAL features + labels at each decision checkpoint of every usable large-holder episode.
Checkpoints: N = 0 (the whale's buy / its partial sell that starts the episode; the window would go live 50 ms later), then the start
of slots s0 + 2, 5, 10, 20, 40, 80, 160, while the whale has not sold yet (its next sell = the dump is after the decision time).
Features use ONLY rows before the decision time (N = 0: up to and incl. the whale's row; N > 0: rows of slots < s0 + N) and, for
history, events CLOSED before it (a book dump counts once its 2-slot follower window is over). Lists: follower bots
(presend/filter/fbots_frozen.json, 297), cohort (overnight/dip/cohort_R1.json, 537 consistent-winner bots), haqq, 4 other dip bots.
Labels (INFERRED replay, f2 cross_val): a window armed at the decision time until min(the whale's dump + 30 ms, decision + CAP slots)
fills at its first crossing whose landing draw fills (4 draws). Per cap: value per fol x exit (curve, gross), P(fill), expected armed
slots (to the fill or the window end). Aux label: haqq bought within 2 slots after the whale's dump (MEASURED).
Out: feats.npz"""
import sys, time, json, pickle, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/follow"
SMS = 212.0; NS = (0, 2, 5, 10, 20, 40, 80, 160); CAPS = (10, 25, 50, 100, 200, 400); W6 = 6e13
DIPB = ("HkQ7hMjy", "CZ77onJz", "6VzXcLk9", "DYXDDrZC")
FEATS = ["N", "kind", "w_pct", "w_sol_in", "w_nbuys", "w_first_rel", "w_cs", "w_dev", "w_unreal", "w_nsells_tok",
         "wh_nd24", "wh_fol24", "wh_ide24", "wh_paid24", "wh_ep24", "wh_gapmed24", "wh_nmint24",
         "age", "vsol", "px_vs_start", "px_vs_ath", "n_tr", "n_wal", "b5", "s5", "b20", "s20", "n5",
         "n_h6", "oth_pct6", "top_oth", "fb_n", "fb_hold", "coh_n", "coh_hold", "hq_n", "hq_hold", "dip_n",
         "tok_nd", "tok_last_ide", "tok_last_fol", "tok_max_fol", "tok_since_last", "tok_ncross", "burst_max", "burst_slots",
         "cr_pct", "cr_sold", "cr_creates24", "hour", "heat10"]
G = {}


def hist(arr_by, key, t_bt, s_c, cols):
    """events of `key` closed before slot s_c (col 0 = close slot) with bt in (t_bt - 24 h, t_bt]"""
    a = arr_by.get(key)
    if a is None: return None
    i1 = np.searchsorted(a[:, 0], s_c, side="left")       # closed before s_c
    m = a[:i1]; m = m[m[:, 1] > t_bt - 86400]
    return m


def work(mints):
    R = G["R"]; X = G["X"]; E = G["E"]; info = G["info"]; st = G["st"]; en = G["en"]
    FB = G["FB"]; COH = G["COH"]; HQ = G["HQ"]; DIP = G["DIP"]
    BDm = G["BDm"]; BDs = G["BDs"]; EPw = G["EPw"]; CRc = G["CRc"]; HEAT = G["HEAT"]; CV = G["CV"]; CVm = G["CVm"]
    out = []
    for m in mints:
        a, b = st[m], en[m]
        sl = R["slot"][a:b].astype(np.int64); us = R["user"][a:b].astype(np.int64); bu = R["buy"][a:b].astype(bool)
        so = R["sol"][a:b] / 1e9; vs = R["vsol"][a:b] / 1e9; bt = R["bt"][a:b].astype(np.int64)
        px = X["px"][a:b]; cc = X["cc"][a:b]; ba = X["ba"][a:b]
        n = b - a
        cbs = np.cumsum(np.where(bu, so, 0)); css = np.cumsum(np.where(bu, 0, so))
        _, fi = np.unique(us, return_index=True); nu = np.zeros(n, np.int64); nu[fi] = 1; cnu = np.cumsum(nu)
        def firstcum(mask):
            z = np.zeros(n, np.int64); u2 = us[mask]; ix = np.flatnonzero(mask)
            if len(ix): _, f2 = np.unique(u2, return_index=True); z[ix[f2]] = 1
            return np.cumsum(z)
        cfb = firstcum(np.isin(us, FB)); ccoh = firstcum(np.isin(us, COH)); cdip = firstcum(np.isin(us, DIP))
        chq = np.cumsum(us == HQ)
        athp = np.maximum.accumulate(px)
        # per-slot buy counts (bursts)
        ub, cb = np.unique(sl[bu], return_counts=True)
        cinf = info[m]; cs = cinf["cs"]; cr = cinf["creator"]
        bd = BDm.get(m)                                          # (row_rel, close slot, fol, ide, slot) sorted by row
        cvx = CVm.get(m)                                         # indices into CV arrays for this mint (sorted by row)
        cvcc = X["cc"][CV["row"][cvx]] if cvx is not None else None
        for e in G["Em"].get(m, []):
            r0 = int(E["r0"][e]) - a; r1 = int(E["r1"][e]); r1 = r1 - a if r1 >= 0 else -1
            w = int(E["user"][e]); s0 = int(sl[r0]); kind = int(E["kind"][e])
            wm = us == w
            wcb = np.cumsum(np.where(wm & bu, so, 0)); wnb = np.cumsum(wm & bu); wns = np.cumsum(wm & ~bu)
            wfirst = np.flatnonzero(wm)[0]
            d_end = cc[r1] + 30.0 if r1 >= 0 else np.inf
            hqf = False
            if r1 >= 0:
                h2 = int(np.searchsorted(sl, sl[r1] + 2, side="right"))
                hqf = bool(np.any((us[r1 + 1:h2] == HQ) & bu[r1 + 1:h2]))
            for N in NS:
                if N == 0: p = r0; t_c = cc[r0] + 50.0; s_c = s0
                else:
                    s_c = s0 + N; p = int(np.searchsorted(sl, s_c, side="left")) - 1; t_c = s_c * SMS
                if r1 >= 0 and (p >= r1 or cc[r1] <= t_c): break
                if r1 < 0 and N > 0 and p >= n - 1 and sl[-1] < s_c - 400: break
                tb = int(bt[p])
                # holdings at p
                uu, li = np.unique(us[:p + 1][::-1], return_index=True); lb = ba[:p + 1][::-1][li]
                pct = lb / 1e13
                oth = (uu != w)
                big = oth & (pct >= 6)
                fbh = int(np.isin(uu[lb > 0], FB).sum()); cohh = int(np.isin(uu[lb > 0], COH).sum())
                hqh = int(np.any((uu == HQ) & (lb > 0)))
                crp = float(pct[uu == cr][0]) if np.any(uu == cr) else 0.0
                crs = int(np.any((us[:p + 1] == cr) & ~bu[:p + 1]))
                # flows
                def win(k):
                    j = int(np.searchsorted(sl, s_c - k, side="left")) - 1
                    return (cbs[p] - (cbs[j] if j >= 0 else 0), css[p] - (css[j] if j >= 0 else 0), p - j)
                b5, s5, n5 = win(5); b20, s20, _ = win(20)
                # bursts over complete slots < s_c
                kb = ub < s_c if N > 0 else ub < s0
                bmax = int(cb[kb].max()) if kb.any() else 0; bsl = int((cb[kb] >= 3).sum())
                # token dumps closed before s_c
                tnd = 0; tli = np.nan; tlf = np.nan; tmf = np.nan; tsl = np.nan
                if bd is not None:
                    c = bd[bd[:, 1] < s_c]
                    if len(c):
                        tnd = len(c); tli = c[-1, 3]; tlf = c[-1, 2]; tmf = c[:, 2].max(); tsl = s_c - c[-1, 4]
                ncr = int((cvcc < t_c).sum()) if cvcc is not None else 0
                # whale history (other events, closed, last 24 h)
                hd = hist(BDs, w, tb, s_c, None)
                wnd = len(hd) if hd is not None else 0
                wfol = float(hd[:, 2].mean()) if wnd else -1.0; wide = float(hd[:, 3].mean()) if wnd else np.nan
                wpaid = float((hd[:, 3] >= 0.02).mean()) if wnd else np.nan
                he = hist(EPw, w, tb, s_c, None)
                if he is not None: he = he[he[:, 4] != m]
                wep = len(he) if he is not None else 0
                wgap = float(np.median(he[:, 2])) if wep else np.nan
                wnm = len(np.unique(he[:, 4])) if wep else 0
                crc = 0
                if cr in CRc:
                    z = CRc[cr]; crc = int(np.searchsorted(z, tb, side="right") - np.searchsorted(z, tb - 86400, side="right")) - 1
                hi_ = int(np.searchsorted(HEAT, s_c, side="left")) - int(np.searchsorted(HEAT, s_c - 1500, side="left"))
                f = [N, kind, ba[p] / 1e13 if wm[p] else float(pct[uu == w][0]) if np.any(uu == w) else 0.0, wcb[p], wnb[p],
                     (sl[wfirst] - cs) if cs is not None else -1, int(cs is not None and sl[wfirst] == cs), int(w == cr),
                     (float(pct[uu == w][0]) * 1e13 * px[p] / 1e9 / max(wcb[p], 1e-3)) if np.any(uu == w) else 0.0, wns[p],
                     wnd, wfol, wide, wpaid, wep, wgap, wnm,
                     (s_c - cs) if cs is not None else -1, vs[p], px[p] / px[r0], px[p] / athp[p], p + 1, cnu[p], b5, s5, b20, s20, n5,
                     int(big.sum()), float(pct[big].sum()), float(pct[oth].max()) if oth.any() else 0.0, cfb[p], fbh, ccoh[p], cohh, chq[p], hqh, cdip[p],
                     tnd, tli, tlf, tmf, tsl, ncr, bmax, bsl, crp, crs, crc, ((tb + 18000) % 86400) // 3600, hi_]
                # labels per cap: the CV indices (relevant crossings) inside the window, and the window end
                lab = []
                for cap in CAPS:
                    wend = min(d_end, t_c + cap * SMS)
                    lab.append((cvx[(cvcc > t_c) & (cvcc <= wend)].tolist() if cvx is not None else [], float(wend)))
                out.append(dict(e=e, m=m, w=w, N=N, t_c=float(t_c), s_c=int(s_c), bt=tb, f=f, hqf=hqf, lab=lab, d_end=float(d_end), r1=int(E["r1"][e])))
    return out


def main():
    t0 = time.time()
    R = np.load(f"{OUT}/tape.npy"); X = dict(np.load(f"{OUT}/rowx.npz"))
    MI = pickle.load(open(f"{OUT}/mints.pkl", "rb")); info = MI["info"]
    st = {int(m): int(a) for m, a in zip(MI["um"], MI["st"])}; en = {int(m): int(b) for m, b in zip(MI["um"], MI["en"])}
    E = dict(np.load(f"{OUT}/episodes.npz")); B = dict(np.load(f"{OUT}/bookdumps.npz")); CV = dict(np.load(f"{OUT}/cross_val.npz"))
    ids, idm = L.ids_map()
    FB = np.array(sorted(idm[w] for w in json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")) if w in idm))
    COH = np.array(sorted(idm[w] for w in json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")) if w in idm))
    DIP = np.array(sorted(i for i, w in enumerate(ids) if w[:8] in DIPB))
    print(f"lists: fbots {len(FB)}, cohort {len(COH)}, dip bots {len(DIP)} ({time.time() - t0:.0f}s)", flush=True)
    hrs = json.load(open(f"{L.D}/hours.json")); good = np.array(sorted({r["h"] for r in hrs["rows"] if r["usable"]}))
    bt = R["bt"].astype(np.int64); sl = R["slot"].astype(np.int64); us = R["user"].astype(np.int64)
    okm = np.zeros(int(MI["um"].max()) + 1, bool)
    for m, c in info.items(): okm[m] = (c["cs"] is not None) and not c["mayhem"] and c["quote_ok"]
    r0 = E["r0"]; em = E["mint"]
    hstart = (bt[r0] + 18000) // 3600 * 3600 - 18000
    eok = okm[em] & np.isin(hstart, good) & (((bt[r0] - L.DAY0) // 86400) <= 6)
    Em = collections.defaultdict(list)
    for e in np.flatnonzero(eok).tolist(): Em[int(em[e])].append(e)
    # book dumps per mint and per seller: (row_rel / seller..., close slot, fol, ide, slot)
    br = B["row"]; bm = R["mint"][br].astype(np.int64)
    BDm = collections.defaultdict(list); BDs = collections.defaultdict(list)
    for r, m, f, i in zip(br.tolist(), bm.tolist(), B["fol"].tolist(), B["ide"].tolist()):
        if not okm[m]: continue
        BDm[m].append((r - st[m], sl[r] + 2, f, i, sl[r]))
        BDs[int(us[r])].append((sl[r] + 3, bt[r], f, i, m))
    BDm = {k: np.array(v, float) for k, v in BDm.items()}
    BDs = {k: np.array(sorted(v), float) for k, v in BDs.items()}
    HEAT = np.sort(np.array([sl[r] for r, m in zip(br.tolist(), bm.tolist()) if okm[m]], np.int64))
    # whale episodes per wallet (close slot = its dump slot + 1; open ones never close): (close slot, bt start, gap slots, -, mint)
    EPw = collections.defaultdict(list)
    for e in np.flatnonzero(okm[em]).tolist():
        r1 = int(E["r1"][e])
        if r1 < 0: continue
        EPw[int(E["user"][e])].append((sl[r1] + 1, bt[r0[e]], sl[r1] - sl[r0[e]], 0, int(em[e])))
    EPw = {k: np.array(sorted(v), float) for k, v in EPw.items()}
    CRc = collections.defaultdict(list)
    for m, c in info.items():
        if c.get("cbt") is not None and c["creator"] >= 0: CRc[c["creator"]].append(c["cbt"])
    CRc = {k: np.sort(np.array(v, np.int64)) for k, v in CRc.items()}
    cvm = R["mint"][CV["row"]].astype(np.int64)
    CVm = collections.defaultdict(list)
    for i, m in enumerate(cvm.tolist()): CVm[m].append(i)
    CVm = {k: np.array(v) for k, v in CVm.items()}
    print(f"usable episodes {int(eok.sum()):,} on {len(Em):,} mints ({time.time() - t0:.0f}s)", flush=True)
    G.update(R=R, X=X, E=E, info=info, st=st, en=en, FB=FB, COH=COH, HQ=MI["haqq"], DIP=DIP, BDm=BDm, BDs=BDs, EPw=EPw, CRc=CRc, HEAT=HEAT, CV=CV, CVm=CVm, Em=Em)
    ms = sorted(Em, key=lambda m: -len(Em[m]))
    chunks = [ms[i::600] for i in range(600)]
    res = []
    with Pool(3) as P:
        for k, o in enumerate(P.imap_unordered(work, chunks)):
            res.extend(o)
            if k % 50 == 0: print(f"  {k}/{len(chunks)} rows {len(res):,} ({time.time() - t0:.0f}s)", flush=True)
    res.sort(key=lambda z: (z["t_c"], z["e"], z["N"]))
    F = np.array([z["f"] for z in res], float)
    meta = np.array([(z["e"], z["m"], z["w"], z["N"], z["t_c"], z["s_c"], z["bt"], z["hqf"], z["d_end"], z["r1"]) for z in res],
                    dtype=[("e", "i8"), ("m", "i8"), ("w", "i8"), ("N", "i4"), ("t_c", "f8"), ("s_c", "i8"), ("bt", "i8"), ("hqf", "?"), ("d_end", "f8"), ("r1", "i8")])
    labs = [[z["lab"][c] for c in range(len(CAPS))] for z in res]
    np.savez_compressed(f"{OUT}/feats.npz", F=F, meta=meta, names=np.array(FEATS), CAPS=np.array(CAPS))
    pickle.dump(labs, open(f"{OUT}/labs.pkl", "wb"))
    print(f"done {len(res):,} checkpoint rows ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
