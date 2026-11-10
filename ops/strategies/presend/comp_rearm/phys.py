#!/usr/bin/env python3
"""Physics check (MEASURED on the chain tape, our wallets removed): every competitor buy -> its own next sell (delay, size, price
drop of that sell alone), and the deepest single-slot drop (vs the price at the end of the previous slot) in the 10 slots after the
buy. Out: comp_buys_<tag>.pkl (one row per competitor buy) used by the trigger builder.  usage: phys.py TAG TAB [D]"""
import sys, pickle, json, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/comp_rearm")
import rlib
from comps import COMP
OUT = "/home/it/sniper-data/comp_rearm"
OUR = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
tag, tab = sys.argv[1], sys.argv[2]
tp = rlib.Tape(tab=tab, with_ours=False); ck = tp.clock()
idm = tp.id_map(); our = {idm[w] for w in OUR if w in idm}
cid = {idm[v]: k for k, v in COMP.items() if v in idm}
rows = []
for mid, (a, e) in tp.span.items():
    ks = [k for k in range(a, e) if tp.user[k] not in our]
    if not any(tp.user[k] in cid and tp.buy[k] for k in ks): continue
    mint = tp.ids[mid]; c = tp.creates.get(mint); s0 = c["slot"] if c else None
    S = np.array([tp.s[k] for k in ks]); P = np.array([tp.vsol[k] / tp.vtok[k] for k in ks])
    for q, k in enumerate(ks):
        u = int(tp.user[k])
        if u not in cid or not tp.buy[k]: continue
        s = int(tp.s[k]); p0 = P[q]
        # own next sell
        sq = next((r for r in range(q + 1, len(ks)) if tp.user[ks[r]] == u and not tp.buy[ks[r]] and tp.s[ks[r]] <= s + 300), None)
        sell = None
        if sq is not None:
            kk = ks[sq]; pb = P[sq - 1]; pa = P[sq]
            sell = dict(dslot=int(tp.s[kk]) - s, dms=ck.cc(int(tp.s[kk]), int(tp.i[kk])) - ck.cc(s, int(tp.i[k])), sol=int(tp.sol[kk]), drop=1 - pa / pb,
                        same_slot=int(tp.s[kk]) == s)
        # deepest single-slot drop in slots s..s+10 (price after each trade vs the price at the end of the previous slot)
        best = 0.0; best_slot = None; n_others_sell = 0
        r = q + 1; prev_end = p0
        while r < len(ks) and S[r] <= s + 10:
            sl = S[r]; ref = prev_end
            while r < len(ks) and S[r] == sl:
                dd = 1 - P[r] / ref
                if dd > best: best = dd; best_slot = int(sl) - s
                if not tp.buy[ks[r]] and tp.user[ks[r]] != u: n_others_sell += 1
                r += 1
            prev_end = P[r - 1]
        n_comp_in = len({int(tp.user[ks[r]]) for r in range(0, q + 1) if tp.user[ks[r]] in cid and tp.buy[ks[r]]})
        rows.append(dict(mint=mint, who=cid[u], slot=s, idx=int(tp.i[k]), j=int(tp.j[k]), bt=int(tp.blockt[k]), sol=int(tp.sol[k]),
                         vsol=int(tp.vsol[k]), age_slots=(s - s0) if s0 else None, sell=sell, maxdrop10=best, maxdrop_slot=best_slot,
                         n_comp=n_comp_in, prev_big_sell=any((not tp.buy[ks[r]]) and tp.sol[ks[r]] >= 1e9 and S[r] >= s - 1 for r in range(max(0, q - 30), q))))
pickle.dump(rows, open(f"{OUT}/comp_buys_{tag}.pkl", "wb"))
print(tag, len(rows), collections.Counter(r["who"] for r in rows).most_common())
