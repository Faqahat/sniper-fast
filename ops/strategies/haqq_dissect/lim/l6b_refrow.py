#!/usr/bin/env python3
"""LIM step 6b (read-only): which tape state is haqq's limit reference? For each LIMITED buy in the RPC sample, scan every
state from 8 slots before his tx up to his tx; a state 'matches' rule x if tokens(spend at that state)/min_out - 1 is within
+-0.05% of x for x in {2.04% (=1/0.98), 5.26% (=1/0.95), 8.11% (=1/0.925), 8.70% (=1/0.92)} or the buy's own best x. Reports the matched state's position
relative to the dump and to his tx (trades ahead of him he had NOT seen = his reaction lag).
Out: data/lim/l6b.txt"""
import json, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
lim = [r for r in pickle.load(open(f"{OUT}/limits.pkl", "rb")) if r["limited"]]
H = {r["sig"]: r for r in pickle.load(open(f"{OUT}/hctx2.pkl", "rb"))}
ids, idm = L.ids_map(); hid = idm[L.HAQQ]
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
mids = np.array(sorted({idm[H[r["sig"]]["mint"]] for r in lim}), np.uint32)
TT = np.asarray(T[np.isin(T["mint"], mids)]); TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
res = []
for r in lim:
    h = H[r["sig"]]; a, b = span[h["mint"]]; R = TT[a:b]
    sl = R["slot"].astype(np.int64); key = sl * 100000 + R["idx"].astype(np.int64)
    vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64)
    p = int(np.searchsorted(key, h["s"] * 100000 + h["i"])); lo = int(np.searchsorted(sl, h["s"] - 8))
    sn = r["spend"] / (1 + S.FEE)
    tok = vt[lo:p] - vs[lo:p] * vt[lo:p] / (vs[lo:p] + sn)
    tol = tok / r["min_out"] - 1
    m = None
    for x in (0.0204, 0.0526, 0.0811, 0.0870):
        hit = np.flatnonzero(np.abs(tol - x) < 0.0005)
        if len(hit): m = (x, lo + int(hit[-1])); break
    rr = dict(r)
    if m:
        k = m[1]; rr.update(rule=m[0], ref_ahead=p - 1 - k, ref_slots=int(h["s"] - sl[k]), ref_is_dump=("d_row" in h and False),
                            ref_ms=float(L.cc(h["s"], h["i"]) - L.cc(int(sl[k]), int(R["idx"][k]))), ref_buy=bool(R["buy"][k]),
                            ref_user_haqq=bool(R["user"][k] == hid or R["signer"][k] == hid),
                            ref_vs_dump=(int(key[k]) - (h["d_slot"] * 100000 + h["d_idx"])) if "d_slot" in h else None)
    res.append(rr)
P(f"# haqq limit reference row (limited buys in the RPC sample, n={len(res)})")
mt = [r for r in res if r.get("rule")]
P(f"matched to a state at exactly +2.04% / +5.26% / +8.11% / +8.70% (2 / 5 / 7.5 / 8% token slippage): {len(mt)} of {len(res)}; rule counts {collections.Counter(r['rule'] for r in mt)}")
P("by size: " + "; ".join(f"{s}: {sum(1 for r in mt if round(r['spend'],3)==s)}/{sum(1 for r in res if round(r['spend'],3)==s)} matched, rules {dict(collections.Counter(r['rule'] for r in mt if round(r['spend'],3)==s))}" for s in sorted({round(r['spend'], 3) for r in res})))
P(f"reference = the dump row itself: {sum(1 for r in mt if r['ref_vs_dump']==0)}; a later row than the dump: {sum(1 for r in mt if r['ref_vs_dump'] and r['ref_vs_dump']>0)}; earlier: {sum(1 for r in mt if r['ref_vs_dump'] is not None and r['ref_vs_dump']<0)}")
P(f"reference row was a sell: {sum(1 for r in mt if not r['ref_buy'])}, a buy: {sum(1 for r in mt if r['ref_buy'])}; his own trade: {sum(1 for r in mt if r['ref_user_haqq'])}")
v = [r["ref_ahead"] for r in mt]
P(f"trades between his reference state and his tx (unseen when he decided): p10/50/90 {np.percentile(v,[10,50,90])}; zero: {100*np.mean(np.array(v)==0):.0f}%")
P(f"chain-clock ms from reference trade to his tx p10/50/90: {np.percentile([r['ref_ms'] for r in mt],[10,50,90]).round(0)}; slots: {collections.Counter(r['ref_slots'] for r in mt).most_common(5)}")
pickle.dump(res, open(f"{OUT}/limits_ref.pkl", "wb"))
open(f"{OUT}/l6b.txt", "w").write("\n".join(out) + "\n")
