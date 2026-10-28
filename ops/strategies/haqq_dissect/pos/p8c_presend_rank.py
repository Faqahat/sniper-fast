#!/usr/bin/env python3
"""pos step 8c (read-only): contention-aware PRE-SEND landing model + the whale-dump re-arm groups with it.
Model (MEASURED, same idea as dv8 c2 rank model): for each of our 1,145 live pre-send fills (dv8 live_presend.pkl), k = n_between
(outside trades between the dump and our fill) and N_w = outside trades after the dump to the end of slot dump+1 (tape, our rows
removed). Replay: k drawn from the live fills in the same N_w bucket (q = k/N_w resampled like c2), fill if price at entry <=
0.88 x pre-dump price (INFERRED engine limit), 2-slot exit, exact followers, 8 draws, 0.40 SOL. Value per fill and per dump; per day;
90% bootstrap over dumps of the pooled per-fill value. Costs: per fill NOW 3.52 mSOL, CHEAP 0.66 (failed tries extra, not counted).
Out: p8c.txt"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name
P = Out(f"{OUT}/p8c.txt")
EDG = (0, 1, 2, 3, 5, 8, 13, 10 ** 6)


def bk(n): return int(np.searchsorted(EDG, n, side="right") - 1)


def main():
    Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    tape = R6.Tape()
    _T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r"); _u = np.asarray(_T["user"]); _keep = ~np.isin(_u, [idm[w] for w in L.WAL.values() if w in idm])
    _mi = np.asarray(_T["mint"])[_keep]; IX = np.asarray(_T["idx"])[_keep][np.argsort(_mi, kind="stable")].astype(np.int64); del _u, _keep, _mi
    # mint spans in the sorted tape
    Tm = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")["mint"]
    our = [idm[w] for w in L.WAL.values() if w in idm]
    mm = np.asarray(Tm)[~np.isin(np.asarray(np.load(f"{L.TAB}/trades.npy", mmap_mode="r")["user"]), our)]
    mm = np.sort(mm, kind="stable")
    um, st = np.unique(mm, return_index=True); en = np.append(st[1:], len(mm)); span = {int(a): (int(b), int(c)) for a, b, c in zip(um, st, en)}
    del mm
    lp = pickle.load(open(f"{L.D}/live_presend.pkl", "rb"))
    q_by = collections.defaultdict(list); nfit = 0
    for x in lp:
        if x.get("res") != "ok" or x.get("n_between") is None or x.get("dslot") is None or x["mint"] not in idm: continue
        a, b = span.get(idm[x["mint"]], (0, 0))
        if b <= a: continue
        sl = tape.sl[a:b]
        j = np.flatnonzero(sl == x["dslot"])
        if not len(j): continue
        # dump row: the tape row in the dump slot with idx == didx (tape idx not kept in Tape; use trades.npy order equivalently)
        lo = a + int(np.searchsorted(sl, x["dslot"], side="left"))
        hi = a + int(np.searchsorted(sl, x["dslot"] + 1, side="right"))
        ixs = IX[lo:hi]; sls = tape.sl[lo:hi]
        dj = np.flatnonzero((sls == x["dslot"]) & (ixs == x["didx"]))
        if not len(dj): continue
        nw = int(hi - (lo + int(dj[-1])) - 1)              # outside trades after the dump to the end of slot dump+1
        q_by[bk(nw)].append(min(x["n_between"], nw) / max(nw, 1) if nw > 0 else 0.0); nfit += 1
    P(f"# pre-send contention model fitted on {nfit} live fills; N_w buckets: " + ", ".join(f"{EDG[k]}+: {len(v)} (k/N_w mean {np.mean(v):.2f})" for k, v in sorted(q_by.items())))
    P("(N_w = outside trades after the dump to the end of slot dump+1, exact rows from the tape)")
    wh = np.flatnonzero(X[:, 2] >= 6.0)
    rng = np.random.default_rng(11); DR = 8
    ps_val = np.zeros(len(M)); ps_fill = np.zeros(len(M)); ideal2 = np.full(len(M), np.nan)
    for i in wh:
        jd = int(M["row"][i]); end = int(M["end"][i]); s0 = int(M["slot"][i])
        pre_px = tape.vs[jd - 1] / tape.vt[jd - 1]
        nwin = int(np.searchsorted(tape.sl[jd + 1:end], s0 + 1, side="right"))
        qs = q_by.get(bk(nwin)) or q_by[max(q_by)]
        vals = []; fills = 0
        for qd in rng.choice(qs, DR):
            k = int(round(qd * nwin)); r = min(jd + 1 + k, end)
            px = tape.vs[r - 1] / tape.vt[r - 1]
            if not (px <= 0.88 * pre_px): vals.append(0.0); continue
            es = int(tape.sl[r - 1]) if r - 1 > jd else s0
            q = tape.qrow(r, end, es, 2); vals.append(tape.joint([(r, q)])[0]); fills += 1
        ps_val[i] = np.mean(vals); ps_fill[i] = fills / DR
        q = tape.qrow(jd + 1, end, s0, 2); ideal2[i] = tape.joint([(jd + 1, q)])[0]
    o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
    kw = {}; prevpay = {}; prevslot = {}; last = None
    for i in o:
        m = int(M["mint"][i])
        if last is None or last[0] != m: kw[i] = 1; last = (m, i); continue
        kw[i] = kw[last[1]] + 1; prevpay[i] = ideal2[last[1]]; prevslot[i] = int(M["slot"][last[1]]); last = (m, i)
    rows = np.array([i for i in wh if usable[i] and np.isfinite(ideal2[i])])
    G = {"first": lambda i: kw[i] == 1,
         "rearm_paid": lambda i: kw[i] >= 2 and prevpay.get(i, -1) >= 0.02 and M["slot"][i] > prevslot[i] + 2,
         "rearm_notpaid": lambda i: kw[i] >= 2 and prevpay.get(i, 1) < 0.02 and M["slot"][i] > prevslot[i] + 2,
         "within2": lambda i: kw[i] >= 2 and M["slot"][i] <= prevslot[i] + 2}
    P("\n| group | dumps | fill share | mSOL per fill [90% boot] | net per fill NOW / CHEAP | SOL/day-window D0..D6 (per-fill value x fills, before costs) | days > 0 |")
    P("|---|---|---|---|---|---|---|")
    br = np.random.default_rng(3)
    for nm, f in G.items():
        v = np.array([i for i in rows if f(i)])
        pf = ps_fill[v]; pv = ps_val[v]
        val = pv.sum() / pf.sum()
        bs = []
        for _ in range(1000):
            ii = br.integers(0, len(v), len(v)); bs.append(pv[ii].sum() / max(pf[ii].sum(), 1e-9))
        pd = [pv[day[v] == d].sum() for d in range(7)]
        P(f"| {nm} | {len(v):,} | {100 * pf.mean():.0f}% | {1000 * val:+.2f} [{1000 * np.percentile(bs, 5):+.2f}..{1000 * np.percentile(bs, 95):+.2f}] | "
          f"{1000 * (val - 0.00352):+.2f} / {1000 * (val - 0.00066):+.2f} | " + " ".join(f"{p:+.2f}" for p in pd) + f" | {sum(p > 0 for p in pd[:6])}/6 |")
    # the re-arm group by seller == the previous whale (same wallet selling again) vs a different whale -- not in uni; skip
    # extra split: re-arm paid group by gap since the previous whale dump
    v = np.array([i for i in rows if G["rearm_paid"](i)])
    gap = np.array([M["slot"][i] - prevslot[i] for i in v])
    P("\nre-arm (previous paid) by slots since the previous whale dump:")
    for a, b in ((3, 5), (6, 10), (11, 25), (26, 100), (101, 10 ** 9)):
        w = v[(gap >= a) & (gap <= b)]
        if len(w): P(f"- {a}-{b}: {len(w):,} dumps, fill {100 * ps_fill[w].mean():.0f}%, per fill {1000 * ps_val[w].sum() / max(ps_fill[w].sum(), 1e-9):+.2f} mSOL")
    P("re-arm (previous paid) by token age at the dump:")
    for a, b in ((0, 10), (10, 30), (30, 120), (120, 600), (600, 10 ** 9)):
        w = v[(M["age"][v] * 0.212 >= a) & (M["age"][v] * 0.212 < b)]
        if len(w): P(f"- age {a}-{b} s: {len(w):,} dumps, fill {100 * ps_fill[w].mean():.0f}%, per fill {1000 * ps_val[w].sum() / max(ps_fill[w].sum(), 1e-9):+.2f} mSOL")
    np.savez(f"{OUT}/p8c.npz", ps_val=ps_val, ps_fill=ps_fill, ideal2=ideal2)
    P.save()


if __name__ == "__main__":
    main()
