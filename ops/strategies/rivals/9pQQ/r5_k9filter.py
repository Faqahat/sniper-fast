#!/usr/bin/env python3
"""Candidate C1 '9pQQ-attention': on a generic reactive-dip universe (outside sell >= 1 SOL, price drop >= 5 %, non-mayhem token
launched in the recording, age >= 5 slots, curve SOL after the dump < 85), paper-buy 0.55 SOL DELTA ms after the dump and sell
after 1 slot (~212 ms) or 6 slots (~1.3 s), cost 4.5 mSOL, 9pQQ's real trades KEPT (it is a real co-trader), and split by 9pQQ's
state on that token at the dump: never traded / round-tripped before (not holding) / holding now.  Rows: -20 % followers
(first 3 slots), without top 5.  Also stratified by trades-so-far on the token (activity confounder).  Nothing is fitted.
-> k9filter.json.  Read-only.  usage: r5_k9filter.py"""
import json, collections
import numpy as np
import tlib9 as L, rlib9 as R

out = {}
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]; s0, bsz = R.blocksizes(r); la = L.launches(r)
    lslot = np.array([la[m]["slot"] if m in la else -1 for m in t.mints]); may = np.array([la[m]["may"] if m in la else True for m in t.mints])
    me = t.u != wid
    drop = 1 - L.price(t.cpost.astype(float)) / L.price(t.cpre.astype(float))
    vs = L.vsol(t.cpost.astype(float)) / 1e9
    cand = np.where(me & (t.tok < 0) & (t.sol >= 1e9) & (drop >= 0.05) & ~may[t.m] & (lslot[t.m] >= 0) & (t.s - lslot[t.m] >= 5) & (vs < 85))[0]
    # 9pQQ state per row: cumulative 9pQQ tokens and trade count on the mint before the row
    h9 = np.cumsum(np.where(~me, t.tok, 0)); c9 = np.cumsum((~me).astype(np.int64))
    res = collections.defaultdict(list); cache = {}
    for j in cand:
        mi = int(t.m[j]); a0 = t.mstart[mi]
        hold = (h9[j] - (h9[a0 - 1] if a0 else 0)) > 1000
        n9 = c9[j] - (c9[a0 - 1] if a0 else 0)
        st = "holding" if hold else ("traded_before" if n9 else "never")
        M = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = M
        jj = j - a0; dcc = M.CC[jj]
        act = "ntr<200" if jj < 200 else ("ntr200-1000" if jj < 1000 else "ntr>=1000")
        for d in (50, 70, 90):
            for hs in (1, 6):
                v = R.trip(M, dcc + d, dcc + d + hs * R.SMS)
                res[(d, hs, st)].append(v)
                if d == 70:
                    res[(d, hs, st, act)].append(v)
                    res[(d, hs, st, "fol")].append(R.trip(M, dcc + d, dcc + d + hs * R.SMS, fol=0.2))
    hrs = (t.bt.max() - t.bt.min()) / 3600
    o = {}
    for k, v in sorted(res.items(), key=lambda kv: str(kv[0])):
        v = np.sort(np.array(v) / 1e9)
        o[" ".join(map(str, k))] = dict(n=len(v), per_day=round(v.sum() / hrs * 24, 2), msol=round(1000 * v.mean(), 2), wo_top5=round(v[:-5].sum(), 2), win=round(float((v > 0).mean()), 3))
    out[L.DAY[r]] = o
    print(L.DAY[r], "dumps", len(cand), flush=True)
    for k in o:
        if k.startswith("70 "): print("  ", k, o[k])
json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/k9filter.json", "w"), indent=1)
