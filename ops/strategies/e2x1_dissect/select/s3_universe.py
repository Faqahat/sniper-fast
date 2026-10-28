#!/usr/bin/env python3
"""SELECT s3 (read-only): the EVENT universe. Every outside trade e (not E2x1) on a SOL-quoted, non-mayhem pump.fun curve aged
0..30 min. Features use rows <= e only (e itself is the possible trigger). Label y = E2x1 has a BUY row after e on that mint
with slot <= slot_e + 1 (he reacts within 1 slot; 99.8 % of his buys come <= 1 slot after the previous trade, MEASURED in s2).
Forward outcomes (market, from px after e): f5/f24/f141 = px at last row with slot <= s+k / px_e - 1; and from entry one slot
later (px after the last row of slot s+1) to the same horizons: g24/g141.
Keeps: all positives + every row of the mints he ever touched (for take-vs-skip inside a token) + a 4 % hash sample of all other
negatives (weight 25). Out: sniper-data/e2x1_dissect/select/U.npz"""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
t0 = time.time()
D = load(); w = int(D["wid"])
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9
vs = D["vsol"] / 1e9; vt = D["vtok"].astype(np.float64); mi = D["mint"].astype(np.int64); bt = D["bt"].astype(np.int64); us = D["user"].astype(np.int64)
N = len(sl); S0 = int(sl.min())
cs = D["cr_slot"][mi]; cbt = D["cr_bt"][mi]; cu = D["cr_user"][mi]
lp = np.log(vs / np.maximum(vt, 1)); LP0 = np.log(30.0 / 1.073e15)
seg_a = np.zeros(N, np.int64)
st = D["span_a"]; en = D["span_b"]; rank = np.zeros(N, np.int64)
for k, (a, b) in enumerate(zip(st, en)): seg_a[a:b] = a; rank[a:b] = k
print("seg", time.time() - t0, flush=True)
K = (mi << 32) | (sl - S0)
first_in_seg = np.arange(N) == seg_a
lp_prev = np.where(first_in_seg, LP0, np.r_[LP0, lp[:-1]])
F = {}
F["age_s"] = (bt - cbt).astype(np.float32)
F["age_sl"] = (sl - cs).astype(np.float32)
F["vsol"] = vs.astype(np.float32)
F["is_buy"] = bu.astype(np.float32)
F["sol"] = so.astype(np.float32)
F["imp"] = (np.exp(lp - lp_prev) - 1).astype(np.float32)
F["by_creator"] = (us == cu).astype(np.float32)
def lp_before(k):                                   # log px after last row with slot < s - k on the mint (else creation px)
    q = np.searchsorted(K, (mi << 32) | np.maximum(sl - k - S0, 0), side="left") - 1
    ok = q >= seg_a
    return np.where(ok, lp[np.maximum(q, 0)], LP0)
for lab, k in (("1s", 5), ("5s", 24), ("30s", 141), ("120s", 566)):
    F["ret_" + lab] = (np.exp(lp - lp_before(k)) - 1).astype(np.float32)
cm = np.maximum.accumulate(lp + rank * 100.0) - rank * 100.0
F["dd_peak"] = (np.exp(lp - np.maximum(cm, LP0)) - 1).astype(np.float32)
F["mult"] = np.exp(lp - LP0).astype(np.float32)
F["peak_mult"] = np.exp(np.maximum(cm, LP0) - LP0).astype(np.float32)
# flows over slots [s-k, s] up to e inclusive, outside rows only (his own rows excluded)
outr = us != w
def csum(x): return np.r_[0.0, np.cumsum(x)]
CB = csum(bu & outr); CS = csum(~bu & outr); CBS = csum(np.where(bu & outr, so, 0)); CSS = csum(np.where(~bu & outr, so, 0))
for lab, k in (("cur", 0), ("1s", 5), ("5s", 24), ("30s", 141)):
    lo = np.searchsorted(K, (mi << 32) | np.maximum(sl - k - S0, 0), side="left")
    lo = np.maximum(lo, seg_a); hi = np.arange(N) + 1
    F["nb_" + lab] = (CB[hi] - CB[lo]).astype(np.float32); F["ns_" + lab] = (CS[hi] - CS[lo]).astype(np.float32)
    F["solin_" + lab] = (CBS[hi] - CBS[lo]).astype(np.float32); F["solout_" + lab] = (CSS[hi] - CSS[lo]).astype(np.float32)
F["ntr"] = (np.arange(N) - seg_a + 1).astype(np.float32)
o = np.lexsort((np.arange(N), us, mi)); fo = np.ones(N, bool); fo[o[1:]] = (mi[o[1:]] != mi[o[:-1]]) | (us[o[1:]] != us[o[:-1]])
CU = np.cumsum(fo); F["nusers"] = (CU - np.where(seg_a > 0, CU[np.maximum(seg_a - 1, 0)], 0) * (seg_a > 0)).astype(np.float32)
del o
crs = np.cumsum(~bu & (us == cu)); F["dev_sells"] = (crs - np.where(seg_a > 0, crs[np.maximum(seg_a - 1, 0)], 0)).astype(np.float32)
crb = csum(np.where(bu & (us == cu), so, 0)); F["dev_buy_sol"] = (crb[np.arange(N) + 1] - crb[seg_a]).astype(np.float32)
CT = csum(np.where(bu, so, 0)); F["tot_in"] = (CT[np.arange(N) + 1] - CT[seg_a]).astype(np.float32)
bund = csum(np.where(bu & (sl == cs) & (us != cu), so, 0)); F["bundle_sol"] = (bund[np.arange(N) + 1] - bund[seg_a]).astype(np.float32)
F["gap_prev_sl"] = np.where(first_in_seg, -1, sl - np.r_[0, sl[:-1]]).astype(np.float32)
# per-user activity: trades before e by this user on any mint (wallet experience) -- causal count via sorted keys
uk = (us << 40) | (sl - S0) << 13 | np.minimum(ix, 8191)
UK = np.sort(uk); F["user_ntr"] = (np.searchsorted(UK, uk) - np.searchsorted(UK, us << 40)).astype(np.float32)
del UK, uk
# creator history: previous creates by the same creator (all creates in the tape window)
cr_slot = D["cr_slot"]; cr_user = D["cr_user"]; okc = cr_slot >= 0
ck = np.sort((cr_user[okc].astype(np.int64) + 1) * (1 << 31) + (cr_slot[okc] - S0 + 10_000_000))
ckey = (cu + 1) * (1 << 31) + (cs - S0 + 10_000_000)
F["cr_prev"] = (np.searchsorted(ck, ckey) - np.searchsorted(ck, (cu + 1) * (1 << 31))).astype(np.float32)
F["cr_prev"][cu < 0] = -1
lt = np.time = bt % 86400; F["hour"] = (((bt + 18000) % 86400) // 3600).astype(np.float32)
# his own state on this mint before e: tokens held (sign), buys so far
mine = us == w
hb = csum(mine & bu); F["my_buys"] = (hb[np.arange(N) + 1] - hb[seg_a]).astype(np.float32)
tk = D["tok"].astype(np.float64)
ht = csum(np.where(mine, np.where(bu, tk, -tk), 0)); F["my_open"] = ((ht[np.arange(N) + 1] - ht[seg_a]) > 1e3).astype(np.float32)
print("features", time.time() - t0, flush=True)
# labels: next E2x1 row after e on the mint
pos_mine = np.flatnonzero(mine)
nxt = np.searchsorted(pos_mine, np.arange(N), side="right")
nm = pos_mine[np.minimum(nxt, len(pos_mine) - 1)]
has = (nxt < len(pos_mine)) & (mi[nm] == mi) & (sl[nm] <= sl + 1)
y = has & bu[nm]
yfirst = y & (F["my_buys"] == 0)
y3 = (nxt < len(pos_mine)) & (mi[nm] == mi) & (sl[nm] <= sl + 3) & bu[nm]
# forward market returns from px_e
def lp_at_or_before(k):
    q = np.searchsorted(K, (mi << 32) | (sl + k - S0), side="right") - 1
    return lp[q]                                   # q >= e always (same mint, slot >= s)
fw = {f"f{k}": (np.exp(lp_at_or_before(k) - lp) - 1).astype(np.float32) for k in (2, 5, 24, 141)}
lp1 = lp_at_or_before(1)
for k in (24, 141): fw[f"g{k}"] = (np.exp(lp_at_or_before(k) - lp1) - 1).astype(np.float32)
# filter & sample
base = (cs >= 0) & (~D["may"][mi]) & (D["solq"][mi]) & outr & (F["age_s"] >= 0) & (F["age_s"] <= 1800)
touched = np.zeros(len(D["cr_slot"]), bool); touched[np.unique(mi[mine])] = True
hsh = ((D["sol"].astype(np.uint64) * np.uint64(2654435761) + sl.astype(np.uint64) * np.uint64(97) + ix.astype(np.uint64)) % np.uint64(1000)).astype(np.int64)
samp = hsh < 40
keep = base & (y3 | touched[mi] | samp)
print("base rows", int(base.sum()), "positives", int((base & y).sum()), "kept", int(keep.sum()), flush=True)
kk = np.flatnonzero(keep)
out = {k: v[kk] for k, v in F.items()}
out.update({k: v[kk] for k, v in fw.items()})
out.update(row=kk, y=y[kk], y3=y3[kk], yfirst=yfirst[kk], samp=samp[kk], touched=touched[mi[kk]], mint=mi[kk], slot=sl[kk], idx=ix[kk], bt=bt[kk],
           user=us[kk], nxt_row=np.where(y, nm, -1)[kk])
np.savez(f"{OUT}/U.npz", **out)
print("saved", time.time() - t0)
