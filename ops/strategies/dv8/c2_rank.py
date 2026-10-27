#!/usr/bin/env python3
"""DV8 step 2b (read-only): why the independent-delay landing model is optimistic, and a contention-aware landing model.
For each live regular fire: N_w = outside trades on the mint after the dump up to the end of slot dump+1 (the contest we land in;
99% of our first copies land in slot +0/+1); k = outside trades ahead of our first landed copy (MEASURED).
Models of k for a replay candidate:
  M_ms   = independent delay draw (s7 / c1 'B'): k = trades with cc < cc_dump + L
  M_rank = k drawn from the live P(k | N_w bucket) (contention-aware), capped at N_w; entry slot = slot of the last trade ahead
Both are scored on the live fires: fill rate and curve P&L vs live; M_rank fitted on one half and scored on the other (FRA->AMS,
AMS->FRA, early->late, late->early). Out: dv8/c2.txt, dv8/rank_model.json"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
NB = (0, 1, 2, 3, 5, 8, 13, 10 ** 6)          # N_w bucket edges [a, b)


def nb(n): return int(np.searchsorted(NB, n, side="right") - 1)


def main():
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    LM = json.load(open(f"{L.D}/landing_model.json"))
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[f["mint"]] for f in F if f["mint"] in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    wid = [idm[w] for w in L.WAL.values()]
    C = []
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: continue
        a, b = span[f["mint"]]; R = TT[a:b]; R = R[~np.isin(R["user"], wid)]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        jd = np.flatnonzero(key == f["ds"] * 100000 + f["di"])
        if not len(jd): continue
        jd = int(jd[-1])
        nw = int(np.searchsorted(sl, f["ds"] + 1, side="right")) - jd - 1
        k = int(np.searchsorted(key, f["us"][0] * 100000 + f["us"][1])) - jd - 1
        C.append(dict(f=f, R=R, jd=jd, nw=nw, k=k, sl=sl, ix=ix))
    P(f"# Contention and our position, {len(C)} live fires (MEASURED)")
    P("| N_w (outside trades dump -> end of slot+1) | fires | k ahead p25/50/75 | k/N_w mean | live fill % |"); P("|---|---|---|---|---|")
    for i in range(len(NB) - 1):
        v = [c for c in C if nb(c["nw"]) == i]
        if not v: continue
        ks = [c["k"] for c in v]
        P(f"| {NB[i]}-{NB[i + 1] - 1 if NB[i + 1] < 10 ** 6 else 'max'} | {len(v)} | {np.percentile(ks, 25):.0f} / {np.median(ks):.0f} / {np.percentile(ks, 75):.0f} | "
          f"{np.mean([min(c['k'], c['nw']) / max(c['nw'], 1) for c in v]):.2f} | {100 * np.mean([c['f']['out'] == 'fill' for c in v]):.0f} |")

    def fit(cs):
        """per N_w bucket: list of fractions q = min(k, N_w)/N_w (k beyond the window kept as 'late' = 1.0 + extra)"""
        m = collections.defaultdict(list)
        for c in cs: m[nb(c["nw"])].append(min(c["k"], c["nw"]) / max(c["nw"], 1) if c["nw"] > 0 else min(c["k"], 3))
        return {i: sorted(v) for i, v in m.items()}

    rng = np.random.default_rng(3)

    def score(cs, model, mode, draws=40):
        res = []
        for c in cs:
            f = c["f"]; R = c["R"]; sl = c["sl"]; jd = c["jd"]; n = len(R)
            vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
            size = f["spend"]; hold = f["hold"] or 5
            tokd = S.entry_tokens(vs[jd], vt[jd], size)
            fl = []; pn = []
            if mode == "ms":
                samp = np.array(LM["near"].get(f["dump_client"]) or LM["near"]["all"]); ccr = L.cc(sl, c["ix"])
            for _ in range(draws):
                if mode == "ms":
                    Lms = samp[rng.integers(0, len(samp))]
                    r = max(int(np.searchsorted(ccr, ccr[jd] + Lms, side="right")), jd + 1)
                    es = max(int(sl[jd]), int((ccr[jd] + Lms) // L.SMS))
                else:
                    qs = model.get(nb(c["nw"])) or model[max(model)]
                    qv = qs[rng.integers(0, len(qs))]
                    k = int(round(qv * c["nw"])) if c["nw"] > 0 else int(qv)
                    r = jd + 1 + k
                    es = int(sl[min(r - 1, n - 1)]) if k > 0 else int(sl[jd])
                if r > n - 1: fl.append(True); pn.append(0.0); continue
                ok = S.entry_tokens(vs[r - 1], vt[r - 1], size) >= tokd / 1.05
                fl.append(ok)
                if ok and sl[-1] >= es + hold:
                    qt = int(np.searchsorted(sl, es + hold, side="right")) - 1
                    pn.append(S.pnl_exact(vs, vt, sol, tk, bu, r, qt, size))
                else: pn.append(0.0)
            res.append((np.mean(fl), np.mean(pn)))
        return np.array(res)

    rows = pickle.load(open(f"{L.D}/c1_rows.pkl", "rb"))
    live_pnl = {(r["run"], r["t"]): r.get("realized", 0.0) for r in rows}
    def live(cs):
        return np.mean([c["f"]["out"] == "fill" for c in cs]), np.array([live_pnl.get((c["f"]["run"], c["f"]["t"]), 0.0) for c in cs])
    P("\n## Models scored on live fires: fill % and curve P&L mSOL/fire (tx costs excluded)")
    P("| test set | n | live fill % | M_ms fill % | M_rank fill % | live mSOL/fire | M_ms mSOL/fire | M_rank mSOL/fire |"); P("|---|---|---|---|---|---|---|---|")
    mid = np.median([c["f"]["t"] for c in C])
    splits = (("AMS (rank fit on FRA)", lambda c: c["f"]["srv"] == "AMS"), ("FRA (rank fit on AMS)", lambda c: c["f"]["srv"] == "FRA"),
              ("late half (fit early)", lambda c: c["f"]["t"] >= mid), ("early half (fit late)", lambda c: c["f"]["t"] < mid))
    tot = []; oos = {}
    for si, (nm, sel) in enumerate(splits):
        te = [c for c in C if sel(c)]; tr = [c for c in C if not sel(c)]
        md = fit(tr)
        a = score(te, None, "ms"); b = score(te, md, "rank")
        if si < 2:
            for c, x, y in zip(te, a, b): oos[(c["f"]["run"], c["f"]["t"])] = (x[1], y[1], y[0])
        lf, lp = live(te)
        P(f"| {nm} | {len(te)} | {100 * lf:.0f} | {100 * a[:, 0].mean():.0f} | {100 * b[:, 0].mean():.0f} | {1000 * lp.mean():+.2f} | {1000 * a[:, 1].mean():+.2f} | {1000 * b[:, 1].mean():+.2f} |")
    md = fit(C)
    json.dump(dict(edges=list(NB), q={str(k): v for k, v in md.items()}), open(f"{L.D}/rank_model.json", "w"))
    b = score(C, md, "rank"); a = score(C, None, "ms"); lf, lp = live(C)
    P(f"| ALL (in-sample rank) | {len(C)} | {100 * lf:.0f} | {100 * a[:, 0].mean():.0f} | {100 * b[:, 0].mean():.0f} | {1000 * lp.mean():+.2f} | {1000 * a[:, 1].mean():+.2f} | {1000 * b[:, 1].mean():+.2f} |")
    g = np.random.default_rng(1); bs = []
    for _ in range(2000):
        ii = g.integers(0, len(C), len(C)); bs.append(1000 * (lp[ii].mean() - b[ii, 1].mean()))
    P(f"- live - M_rank: {1000 * (lp.mean() - b[:, 1].mean()):+.2f} mSOL/fire [5-95%: {np.percentile(bs, 5):+.2f} .. {np.percentile(bs, 95):+.2f}]")
    bs2 = []
    for _ in range(2000):
        ii = g.integers(0, len(C), len(C)); bs2.append(1000 * (lp[ii].mean() - a[ii, 1].mean()))
    P(f"- live - M_ms: {1000 * (lp.mean() - a[:, 1].mean()):+.2f} mSOL/fire [5-95%: {np.percentile(bs2, 5):+.2f} .. {np.percentile(bs2, 95):+.2f}]")
    pf = [dict(run=c["f"]["run"], t=c["f"]["t"], srv=c["f"]["srv"], m2=c["f"]["m2"], nw=c["nw"], k=c["k"], fill=c["f"]["out"] == "fill", live=float(l),
               ms_is=float(x[1]), rank_is=float(y[1]), ms_oos=oos[(c["f"]["run"], c["f"]["t"])][0], rank_oos=oos[(c["f"]["run"], c["f"]["t"])][1],
               rank_fill_oos=oos[(c["f"]["run"], c["f"]["t"])][2]) for c, l, x, y in zip(C, lp, a, b)]
    pickle.dump(pf, open(f"{L.D}/c2_perfire.pkl", "wb"))
    o = np.array([p["rank_oos"] for p in pf]); lv = np.array([p["live"] for p in pf])
    P("\n## Shape of the gap: live vs M_rank (out-of-sample by server) per quintile of the modelled P&L (mSOL/fire)")
    P("| quintile | n | modelled mean | live mean | live - modelled |"); P("|---|---|---|---|---|")
    qs = np.quantile(o, [0, .2, .4, .6, .8, 1.0])
    for i in range(5):
        m = (o >= qs[i]) & (o <= qs[i + 1]) if i == 4 else (o >= qs[i]) & (o < qs[i + 1])
        P(f"| Q{i + 1} | {m.sum()} | {1000 * o[m].mean():+.2f} | {1000 * lv[m].mean():+.2f} | {1000 * (lv[m] - o[m]).mean():+.2f} |")
    A = np.vstack([o, np.ones(len(o))]).T; cf = np.linalg.lstsq(A, lv, rcond=None)[0]
    P(f"- OLS live = {cf[0]:.2f} x modelled {1000 * cf[1]:+.2f} mSOL (per fire)")
    open(f"{L.D}/c2.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
