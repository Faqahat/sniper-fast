#!/usr/bin/env python3
"""pos step 8b (read-only): the p8 whale-dump groups with REALISTIC entries.
 pre-send style: entry k trades after the dump, k drawn from our MEASURED live pre-send fills (dv8 live_presend.pkl, n_between of
   1,145 fills: 0 61%, 1 20%, 2 8%, 3+ 11%), capped at the trades left in the dump's slot +1; it fills only if the price at our entry is
   <= 0.88 x the pre-dump price (the engine's pre-send limit, --presend-live-drop 0.12, INFERRED as relative to the pre-dump price);
   2-slot exit; 8 draws. Value per DUMP (0 when no fill) and per fill.
 reactive (M2) style: the dv8 rank model (contention-aware, +5% guard), 5-slot exit, calibrated 0.61 x model - 1.17 mSOL.
 Costs not subtracted (per fill: NOW 3.52 mSOL, CHEAP 0.66). Out: p8b.txt"""
import sys, json, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name, boot_sum
P = Out(f"{OUT}/p8b.txt")
FEE = 0.0125; SIZE = 0.4


def main():
    Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]; R = Z["R"]; ES = Z["ES"]
    P5 = np.load(f"{OUT}/p5.npz")
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    lp = pickle.load(open(f"{L.D}/live_presend.pkl", "rb"))
    kd = np.array([x["n_between"] for x in lp if x.get("res") == "ok" and x.get("n_between") is not None])
    wh = np.flatnonzero(X[:, 2] >= 6.0)
    tape = R6.Tape(); rng = np.random.default_rng(5)
    DR = 8
    ps_val = np.zeros(len(M)); ps_fill = np.zeros(len(M)); ideal2 = np.full(len(M), np.nan)
    for i in wh:
        jd = int(M["row"][i]); end = int(M["end"][i]); s0 = int(M["slot"][i])
        pre_px = tape.vs[jd - 1] / tape.vt[jd - 1] if jd > 0 else np.nan
        nwin = int(np.searchsorted(tape.sl[jd + 1:end], s0 + 1, side="right"))
        vals = []; fills = 0
        for k in rng.choice(kd, DR):
            k = int(min(k, nwin)); r = min(jd + 1 + k, end)
            px = tape.vs[r - 1] / tape.vt[r - 1]
            if not (px <= 0.88 * pre_px): vals.append(0.0); continue
            es = int(tape.sl[r - 1]) if r - 1 > jd else s0
            q = tape.qrow(r, end, es, 2); vals.append(tape.joint([(r, q)])[0]); fills += 1
        ps_val[i] = np.mean(vals); ps_fill[i] = fills / DR
        r = jd + 1; q = tape.qrow(r, end, s0, 2); ideal2[i] = tape.joint([(r, q)])[0]
    # groups (same as p8): k-th whale dump on the token, previous whale dump's 2-slot ideal result
    o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
    kw = {}; prevpay = {}; prevslot = {}; last = None
    for i in o:
        m = int(M["mint"][i])
        if last is None or last[0] != m: kw[i] = 1; last = (m, i); continue
        kw[i] = kw[last[1]] + 1; prevpay[i] = ideal2[last[1]]; prevslot[i] = int(M["slot"][last[1]]); last = (m, i)
    ev = P5["ev"]; fr = P5["fr"]; cal = 0.61 * ev - 0.00117
    rows = [i for i in wh if usable[i] and np.isfinite(ideal2[i]) and np.isfinite(P5["ev"][i]) and P5["valid"][i]]
    groups = [("1st whale dump on the token", lambda i: kw[i] == 1),
              ("2nd+ whale dump, previous paid >= +5% (closed)", lambda i: kw[i] >= 2 and prevpay.get(i, -1) >= 0.02 and M["slot"][i] > prevslot[i] + 2),
              ("2nd+ whale dump, previous < +5% (closed)", lambda i: kw[i] >= 2 and prevpay.get(i, 1) < 0.02 and M["slot"][i] > prevslot[i] + 2),
              ("2nd+ whale dump within 2 slots of the previous", lambda i: kw[i] >= 2 and M["slot"][i] <= prevslot[i] + 2)]
    P(f"# Whale dumps (>= 6% supply single sell), usable non-mayhem with valid exits: {len(rows):,}; pre-send k draws from {len(kd)} live fills")
    P("| group | dumps | ideal 2-slot mSOL/dump | pre-send style: fill share | pre-send mSOL per fill [90%] | pre-send mSOL per dump | reactive rank: fill | reactive mSOL/attempt (model) | reactive calibrated mSOL/attempt | D0..D5 pre-send per fill | days > 0 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for nm, f in groups:
        v = np.array([i for i in rows if f(i)])
        if not len(v): continue
        pf = ps_fill[v]; pv = ps_val[v]
        per_fill = pv.sum() / max(pf.sum(), 1e-9)
        w = np.where(pf > 0, pv / np.maximum(pf, 1e-9), np.nan); ww = w[np.isfinite(w)]
        lo, hi = boot_sum(ww / len(ww)) if len(ww) else (0, 0)
        pd = []
        for d in range(6):
            m = day[v] == d
            pd.append(1000 * pv[m].sum() / max(pf[m].sum(), 1e-9) if m.any() else float("nan"))
        P(f"| {nm} | {len(v):,} | {1000 * np.nanmean(ideal2[v]):+.2f} | {100 * pf.mean():.0f}% | {1000 * per_fill:+.2f} [{1000 * lo:+.2f}..{1000 * hi:+.2f}] | {1000 * pv.mean():+.2f} | "
          f"{100 * fr[v].mean():.0f}% | {1000 * ev[v].mean():+.2f} | {1000 * cal[v].mean():+.2f} | " + " ".join(f"{p:+.1f}" for p in pd) + f" | {sum(p > 0 for p in pd if p == p)}/6 |")
    np.savez(f"{OUT}/p8b.npz", ps_val=ps_val, ps_fill=ps_fill, ideal2=ideal2)
    P.save()


if __name__ == "__main__":
    main()
