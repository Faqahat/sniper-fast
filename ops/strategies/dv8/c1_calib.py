#!/usr/bin/env python3
"""DV8 step 2 (read-only): calibrate the replay against OUR live regular fires (all runs, dv8/fires_tape.pkl).
Tape rows of the fire's mint with BOTH our wallets' rows removed. Per fire:
  realized  = curve-level P&L of our own buy + sell trades on the mint (dump slot .. +60 slots), from the tape TradeEvents
              (sol in/out with the actual fee bps; tx costs NOT included) - MEASURED
  A_vs / A_ex = replay with our buy at its ACTUAL landed position and our sell at its ACTUAL position, actual spend;
              follower model vshift (s7) / exact (buys keep SOL, sells keep tokens)
  A_tm      = exact, actual entry, timer exit (last trade of slot entry+hold) - what the universe replay uses
  B         = MODELLED landing: L ms drawn from our measured first-copy delay sample (same leader client, l2), 40 draws;
              fill if entry tokens >= post-dump tokens / 1.05 (engine min_out, checked 99.7% on tape); exact model, timer exit.
Calibration per fill = realized - A_tm (what the universe replay misses after entry), and per fire = live - B (whole chain).
Out: dv8/c1.txt, dv8/c1_rows.pkl"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def boot(v, n=2000, seed=5, f=np.mean):
    v = np.asarray(v, float); g = np.random.default_rng(seed)
    b = [f(v[g.integers(0, len(v), len(v))]) for _ in range(n)]
    return np.percentile(b, 5), np.percentile(b, 95)


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
    wid = {s: idm[w] for s, w in L.WAL.items()}
    rng = np.random.default_rng(11)
    rows = []
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: continue
        a, b = span[f["mint"]]; R = TT[a:b]
        mine = (R["user"] == wid[f["srv"]]) & (R["slot"] >= f["ds"]) & (R["slot"] <= f["ds"] + 60)
        anyours = np.isin(R["user"], list(wid.values()))
        O = R[mine]; R = R[~anyours]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        dk = f["ds"] * 100000 + f["di"]; jd = np.flatnonzero(key == dk)
        if not len(jd): continue
        jd = int(jd[-1]); n = len(R)
        hold = f["hold"] or 5
        row = dict(run=f["run"], srv=f["srv"], t=f["t"], out=f["out"], spend=f["spend"], hold=hold, client=f["dump_client"], n_ahead=f["n_ahead"])
        # ---- realized curve P&L from our own trade rows
        ob = O[O["buy"] == 1]; osl = O[O["buy"] == 0]
        fr = lambda x: (x["fee_bps"].astype(float) + x["cfee_bps"].astype(float)) / 1e4
        if f["out"] == "fill" and len(ob) and len(osl):
            cost = float((ob["sol"] / 1e9 * (1 + fr(ob))).sum()); got = float((osl["sol"] / 1e9 * (1 - fr(osl))).sum())
            row["realized"] = got - cost; row["spend_act"] = cost
            bk = int(ob["slot"][0]) * 100000 + int(ob["idx"][0]); sk = int(osl["slot"][-1]) * 100000 + int(osl["idx"][-1])
            r = int(np.searchsorted(key, bk)); q = int(np.searchsorted(key, sk)) - 1
            row["sell_dslots"] = int(osl["slot"][-1]) - int(ob["slot"][0])
            size = float(ob["sol"][0] / 1e9 * (1 + fr(ob)[0]))
            if r >= 1:
                row["A_vs"] = S.pnl_vshift(vs, vt, r, q, size)
                row["A_ex"] = S.pnl_exact(vs, vt, sol, tk, bu, r, q, size)
                qt = int(np.searchsorted(sl, int(ob["slot"][0]) + hold, side="right")) - 1
                if sl[-1] >= int(ob["slot"][0]) + hold:
                    row["A_tm"] = S.pnl_exact(vs, vt, sol, tk, bu, r, qt, size)
                    row["A_tm_vs"] = S.pnl_vshift(vs, vt, r, qt, size)
        # ---- modelled landing (B), 40 draws from the measured delay sample of the dump leader's client class
        samp = np.array(LM["near"].get(f["dump_client"]) or LM["near"]["all"])
        ccr = L.cc(sl, ix); cd = ccr[jd]
        vd = vs[jd]; td = vt[jd]; size = f["spend"]
        tokd = S.entry_tokens(vd, td, size)
        fills = []; pn = []; nah = []
        for Lms in samp[rng.integers(0, len(samp), 40)]:
            r = max(int(np.searchsorted(ccr, cd + Lms, side="right")), jd + 1)
            nah.append(r - jd - 1)
            if r > n - 1: continue
            ok = S.entry_tokens(vs[r - 1], vt[r - 1], size) >= tokd / 1.05
            fills.append(ok)
            es = max(int(sl[jd]), int((cd + Lms) // L.SMS))
            if ok and sl[-1] >= es + hold:
                qt = int(np.searchsorted(sl, es + hold, side="right")) - 1
                pn.append(S.pnl_exact(vs, vt, sol, tk, bu, r, qt, size))
            else: pn.append(0.0)
        row["B_fill"] = float(np.mean(fills)) if fills else np.nan; row["B_pnl"] = float(np.mean(pn)) if pn else np.nan; row["B_nahead"] = float(np.mean(nah))
        rows.append(row)
    pickle.dump(rows, open(f"{L.D}/c1_rows.pkl", "wb"))
    P(f"# Replay vs live, our regular fires (all runs), n = {len(rows)} fires on tape")
    fl = [r for r in rows if "A_tm" in r]
    P(f"\n## 1. Fills (n={len(fl)}): realized curve P&L vs replay at the ACTUAL positions (mSOL per fill, at actual spend ~{np.mean([r['spend_act'] for r in fl]):.2f} SOL; tx costs excluded)")
    P("| quantity | mean | 5-95% (bootstrap) | sum SOL |"); P("|---|---|---|---|")
    for k, nm in (("realized", "realized (tape, our trades)"), ("A_vs", "replay vshift, actual entry + actual sell"), ("A_ex", "replay exact, actual entry + actual sell"),
                  ("A_tm", "replay exact, actual entry, timer exit"), ("A_tm_vs", "replay vshift, actual entry, timer exit")):
        v = [r[k] for r in fl]; lo, hi = boot(v)
        P(f"| {nm} | {1000 * np.mean(v):+.2f} | {1000 * lo:+.2f} .. {1000 * hi:+.2f} | {np.sum(v):+.3f} |")
    for k in ("A_ex", "A_tm", "A_tm_vs"):
        g = np.array([r["realized"] - r[k] for r in fl]); lo, hi = boot(g)
        P(f"- gap realized - {k}: {1000 * g.mean():+.2f} mSOL/fill [{1000 * lo:+.2f} .. {1000 * hi:+.2f}], median {1000 * np.median(g):+.2f}")
    P(f"- our sell landed (slots after our buy) p10/50/90: {np.percentile([r['sell_dslots'] for r in fl], [10, 50, 90])}; hold config {collections.Counter(r['hold'] for r in fl)}")
    P(f"\n## 2. Whole chain: live outcome vs replay with MODELLED landing on the same {len(rows)} fires")
    P(f"- fill rate: live {100 * np.mean([r['out'] == 'fill' for r in rows]):.1f}% vs modelled {100 * np.nanmean([r['B_fill'] for r in rows]):.1f}%")
    P(f"- outside trades ahead: live mean {np.mean([r['n_ahead'] for r in rows]):.2f} vs modelled {np.mean([r['B_nahead'] for r in rows]):.2f}")
    live_sum = sum(r.get("realized", 0.0) for r in rows); B_sum = np.nansum([r["B_pnl"] for r in rows])
    P(f"- curve P&L (no tx costs): live {live_sum:+.3f} SOL vs modelled {B_sum:+.3f} SOL over {len(rows)} fires -> gap {1000 * (live_sum - B_sum) / len(rows):+.2f} mSOL/fire")
    P("\n| group | n | live fill % | modelled fill % | live curve P&L mSOL/fire | modelled mSOL/fire |"); P("|---|---|---|---|---|---|")
    for nm, sel in (("FRA", lambda r: r["srv"] == "FRA"), ("AMS", lambda r: r["srv"] == "AMS"), ("bam", lambda r: r["client"] == "bam"),
                    ("harmonic", lambda r: r["client"] == "harmonic"), ("jito", lambda r: r["client"] == "jito"),
                    ("before 10-25 23:15", lambda r: r["t"] < 1793038500 - 86400), ("after 10-25 23:15", lambda r: r["t"] >= 1793038500 - 86400)):
        v = [r for r in rows if sel(r)]
        if not v: continue
        P(f"| {nm} | {len(v)} | {100 * np.mean([r['out'] == 'fill' for r in v]):.0f} | {100 * np.nanmean([r['B_fill'] for r in v]):.0f} | "
          f"{1000 * np.mean([r.get('realized', 0) for r in v]):+.2f} | {1000 * np.nanmean([r['B_pnl'] for r in v]):+.2f} |")
    open(f"{L.D}/c1.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
