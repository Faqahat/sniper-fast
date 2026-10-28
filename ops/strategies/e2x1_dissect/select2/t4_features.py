#!/usr/bin/env python3
"""select2 t4: candidate universe + CAUSAL features from five families (all from rows at or before the trigger event e):
  MKT  market shape (same as select/s3)        WAL  trigger-wallet reputation (prior history on the tape, cohorts, E2x1 follow history)
  TX   trigger tx shape (joined by sigh to the raw-recording scan, t3)    TOK  token participants before e (cohort buyers, Grozoe, his own state)
  CRE  creator / launch (creator history, create-slot bundle, dev buy, metadata)   TIM  timing (hour, slot-in-window, his recent activity)
Universe: outside trade events e (not E2x1) on SOL-quoted non-mayhem curves aged 0..30 min. Label y: E2x1 BUY on that mint
within 1 slot after e (next E2x1 row). ysib: same for Grozoe2L. Keep all y|ysib positives + 4 % hash sample (weight 25).
Out: OUT/U2.npz (features float32 + keys)."""
import sys, json, time, hashlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)
D = load(); w = int(D["wid"]); sib = int(D["sibid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9
vs = D["vsol"] / 1e9; vt = D["vtok"].astype(np.float64); mi = D["mint"].astype(np.int64); bt = D["bt"].astype(np.int64); us = D["user"].astype(np.int64)
tk = D["tok"].astype(np.float64); sigh = D["sigh"]
N = len(sl); S0 = int(sl.min()); NM = len(D["cr_slot"]); NU = len(US)
cs = D["cr_slot"][mi]; cbt = D["cr_bt"][mi]; cu = D["cr_user"][mi]
seg_a = np.zeros(N, np.int64); st = D["span_a"]; en = D["span_b"]; rank = np.zeros(N, np.int64)
for k, (a, b) in enumerate(zip(st, en)): seg_a[a:b] = a; rank[a:b] = k
K = (mi << 32) | (sl - S0)
first_in_seg = np.arange(N) == seg_a
lp = np.log(vs / np.maximum(vt, 1)); LP0 = np.log(30.0 / 1.073e15)
lp_prev = np.where(first_in_seg, LP0, np.r_[LP0, lp[:-1]])
def csum(x): return np.r_[0.0, np.cumsum(x, dtype=np.float64)]
AR = np.arange(N)
# labels + universe mask FIRST so every feature is stored only on kept rows (memory)
def next_label(who):
    pos = np.flatnonzero(us == who); nxt = np.searchsorted(pos, AR, side="right"); nm = pos[np.minimum(nxt, len(pos) - 1)]
    has = (nxt < len(pos)) & (mi[nm] == mi) & (sl[nm] <= sl + 1)
    return has & bu[nm], np.where(has & bu[nm], nm, -1)
y, nxt_row = next_label(w); ysib, nxt_sib = next_label(sib)
outr = us != w
age_s_full = (bt - cbt)
base = (cs >= 0) & (~D["may"][mi]) & (D["solq"][mi]) & (vs > 0) & outr & (age_s_full >= 0) & (age_s_full <= 1800)   # vs>0: drops non-SOL-quoted curves (pump/other quote mints decode with sol=0)
hsh = ((D["sol"].astype(np.uint64) * np.uint64(2654435761) + sl.astype(np.uint64) * np.uint64(97) + ix.astype(np.uint64)) % np.uint64(1000)).astype(np.int64)
samp = hsh < 40
keep = base & (y | ysib | samp); kk = np.flatnonzero(keep)
log("base", int(base.sum()), "y", int((base & y).sum()), "ysib", int((base & ysib).sum()), "kept", len(kk))
class Sub(dict):
    def __setitem__(self, k, v):
        v = np.asarray(v); super().__setitem__(k, (v[kk] if len(v) == N else v).astype(np.float32))
F = Sub()
log("base")
# ------------------------------------------------------------------ MKT (select/s3) ------------------------------------------
F["age_s"] = (bt - cbt).astype(np.float32); F["age_sl"] = (sl - cs).astype(np.float32); F["vsol"] = vs.astype(np.float32)
F["is_buy"] = bu.astype(np.float32); F["sol"] = so.astype(np.float32); F["imp"] = (np.exp(lp - lp_prev) - 1).astype(np.float32)
F["by_creator"] = (us == cu).astype(np.float32)
def lp_before(k):
    q = np.searchsorted(K, (mi << 32) | np.maximum(sl - k - S0, 0), side="left") - 1
    return np.where(q >= seg_a, lp[np.maximum(q, 0)], LP0)
for lab, k in (("1s", 5), ("5s", 24), ("30s", 141), ("120s", 566)): F["ret_" + lab] = (np.exp(lp - lp_before(k)) - 1).astype(np.float32)
cm = np.maximum.accumulate(lp + rank * 100.0) - rank * 100.0
F["dd_peak"] = (np.exp(lp - np.maximum(cm, LP0)) - 1).astype(np.float32); F["mult"] = np.exp(lp - LP0).astype(np.float32)
F["peak_mult"] = np.exp(np.maximum(cm, LP0) - LP0).astype(np.float32)
CB = csum(bu & outr); CS = csum(~bu & outr); CBS = csum(np.where(bu & outr, so, 0)); CSS = csum(np.where(~bu & outr, so, 0))
for lab, k in (("cur", 0), ("1s", 5), ("5s", 24), ("30s", 141)):
    lo = np.maximum(np.searchsorted(K, (mi << 32) | np.maximum(sl - k - S0, 0), side="left"), seg_a); hi = AR + 1
    F["nb_" + lab] = (CB[hi] - CB[lo]).astype(np.float32); F["ns_" + lab] = (CS[hi] - CS[lo]).astype(np.float32)
    F["solin_" + lab] = (CBS[hi] - CBS[lo]).astype(np.float32); F["solout_" + lab] = (CSS[hi] - CSS[lo]).astype(np.float32)
F["ntr"] = (AR - seg_a + 1).astype(np.float32)
o = np.lexsort((AR, us, mi)); fo = np.ones(N, bool); fo[o[1:]] = (mi[o[1:]] != mi[o[:-1]]) | (us[o[1:]] != us[o[:-1]]); del o
CU_ = np.cumsum(fo); F["nusers"] = (CU_ - np.where(seg_a > 0, CU_[np.maximum(seg_a - 1, 0)], 0) * (seg_a > 0)).astype(np.float32)
crs = np.cumsum(~bu & (us == cu)); F["dev_sells"] = (crs - np.where(seg_a > 0, crs[np.maximum(seg_a - 1, 0)], 0)).astype(np.float32)
crb = csum(np.where(bu & (us == cu), so, 0)); F["dev_buy_sol"] = (crb[AR + 1] - crb[seg_a]).astype(np.float32)
CT = csum(np.where(bu, so, 0)); F["tot_in"] = (CT[AR + 1] - CT[seg_a]).astype(np.float32)
CTO = csum(np.where(~bu, so, 0)); F["tot_out"] = (CTO[AR + 1] - CTO[seg_a]).astype(np.float32)
bund = csum(np.where(bu & (sl == cs) & (us != cu), so, 0)); F["bundle_sol"] = (bund[AR + 1] - bund[seg_a]).astype(np.float32)
bundn = csum((bu & (sl == cs) & (us != cu)).astype(float)); F["bundle_n"] = (bundn[AR + 1] - bundn[seg_a]).astype(np.float32)
F["gap_prev_sl"] = np.where(first_in_seg, -1, sl - np.r_[0, sl[:-1]]).astype(np.float32)
F["hour"] = (((bt + 18000) % 86400) // 3600).astype(np.float32)
mine = us == w; hb = csum(mine & bu); F["my_buys"] = (hb[AR + 1] - hb[seg_a]).astype(np.float32)
ht = csum(np.where(mine, np.where(bu, tk, -tk), 0)); F["my_open"] = ((ht[AR + 1] - ht[seg_a]) > 1e3).astype(np.float32)
log("MKT")
# ------------------------------------------------------------------ WAL: trigger wallet reputation ---------------------------
# chain order per user: sort by (user, slot, idx, row)
ou = np.lexsort((AR, ix, sl, us)); uu = us[ou]
ustart = np.r_[0, np.flatnonzero(uu[1:] != uu[:-1]) + 1]; ustart_of = np.zeros(N, np.int64); ustart_of[ustart] = ustart
ustart_of = np.maximum.accumulate(ustart_of)            # in ou-order: index of the user's first row
pos_in_u = np.arange(N) - ustart_of                     # prior trades (exclusive)
def ucum_excl(x):                                       # exclusive cumulative sum of x along chain order within user, mapped back to rows
    c = np.cumsum(x[ou], dtype=np.float64); c = c - x[ou] ; c = c - (c[ustart_of] - 0)   # subtract value at segment start (exclusive)
    out = np.empty(N); out[ou] = c; return out
# NOTE: c[ustart_of] is the exclusive cum at the segment's first row = cum of all rows before the segment -> subtract to get in-segment
u_ntr_full = np.empty(N, np.float32); u_ntr_full[ou] = pos_in_u; F["u_ntr"] = u_ntr_full
u_nbuy_full = ucum_excl(bu.astype(float)); F["u_nbuy"] = u_nbuy_full; F["u_nsell"] = u_ntr_full - u_nbuy_full
u_solin_full = ucum_excl(np.where(bu, so, 0.0)); F["u_solin"] = u_solin_full; F["u_solout"] = ucum_excl(np.where(~bu, so, 0.0))
F["u_nmint"] = ucum_excl(fo.astype(float)).astype(np.float32)
F["u_create_buys"] = ucum_excl((bu & (sl == cs)).astype(float)).astype(np.float32)
F["u_first_slot_buys"] = ucum_excl((bu & (sl <= cs + 1)).astype(float)).astype(np.float32)
# first seen
fb = np.empty(N, np.int64); fb[ou] = bt[ou][ustart_of]; F["u_age_s"] = (bt - fb).astype(np.float32)
# his follow history on this wallet: E2x1 bought <= 1 slot after this wallet's earlier trades (only trades with slot <= s-2 count)
yo = np.cumsum(y[ou].astype(np.float64)); yo = np.r_[0.0, yo]
ukey = (us << 40) | (sl - S0 + 2); ukey_o = ukey[ou]                           # sorted ascending within user (lexsort by slot)
q = np.searchsorted(ukey_o, (us << 40) | (sl - S0), side="left")              # first row in user with slot >= s-2+... -> rows with slot+2 <= s  i.e. slot <= s-2
base_i = ustart_of; tmp = np.empty(N, np.int64); tmp[ou] = base_i
u_follow_full = (yo[q] - yo[tmp]); F["u_follow_n"] = u_follow_full
F["u_follow_rate"] = u_follow_full / np.maximum(q - tmp, 1)
F["u_follow_rate_sm"] = (u_follow_full + 0.3) / (np.maximum(q - tmp, 0) + 100)
F["u_prior_n2"] = (q - tmp)
# sib follow history (Grozoe followed this wallet before)
yso = np.r_[0.0, np.cumsum(ysib[ou].astype(np.float64))]; F["u_sibfollow_n"] = (yso[q] - yso[tmp])
del yo, yso
# round trips per (user, mint): close when position <= 1e-4 * cumulative bought (sell row)
om = np.lexsort((AR, ix, sl, mi, us)); um_ = (us[om] << 32) | mi[om]
gstart = np.r_[0, np.flatnonzero(um_[1:] != um_[:-1]) + 1]; gs_of = np.zeros(N, np.int64); gs_of[gstart] = gstart; gs_of = np.maximum.accumulate(gs_of)
tko = np.where(bu, tk, -tk)[om]; cpos = np.cumsum(tko) - (np.cumsum(tko) - tko)[gs_of]   # inclusive cum within (user,mint) group
cbuy = np.cumsum(np.where(bu, tk, 0)[om]); cbuy = cbuy - (cbuy - np.where(bu, tk, 0)[om])[gs_of]
cnet = np.cumsum(np.where(bu, -so, so)[om]); cnet = cnet - (cnet - np.where(bu, -so, so)[om])[gs_of]
cin = np.cumsum(np.where(bu, so, 0)[om]); cin = cin - (cin - np.where(bu, so, 0)[om])[gs_of]
close = (~bu[om]) & (cpos <= cbuy * 1e-4) & (cbuy > 0)
# trip pnl = cnet at close - cnet at previous close in group
ci = np.flatnonzero(close)
pc_net = np.r_[0.0, cnet[ci[:-1]]]; pc_in = np.r_[0.0, cin[ci[:-1]]]
same_g = np.r_[False, gs_of[ci[1:]] == gs_of[ci[:-1]]]
trip_pnl = np.zeros(N); trip_cost = np.zeros(N)
trip_pnl[ci] = cnet[ci] - np.where(same_g, pc_net, 0.0); trip_cost[ci] = cin[ci] - np.where(same_g, pc_in, 0.0)
tp = np.empty(N); tp[om] = trip_pnl; tc = np.empty(N); tc[om] = trip_cost; cl = np.zeros(N, bool); cl[om] = close
u_trips_full = ucum_excl(cl.astype(float)); F["u_trips"] = u_trips_full
u_pnl_full = ucum_excl(tp); u_cost_full = ucum_excl(tc); F["u_trip_pnl"] = u_pnl_full; F["u_trip_cost"] = u_cost_full
u_wins_full = ucum_excl((cl & (tp > 0)).astype(float)); F["u_wins"] = u_wins_full
F["u_winrate"] = (u_wins_full + 1) / (u_trips_full + 2)
u_rps_full = u_pnl_full / np.maximum(u_cost_full, 0.5); F["u_ret_per_sol"] = u_rps_full
F["u_open_mints"] = ucum_excl(fo.astype(float)) - u_trips_full   # rough: mints entered minus trips closed
# hold time proxy: slots from a (user,mint) group's first buy to the close row, summed causally
gfirst_sl = sl[om][gs_of]; hold_sl = np.where(close, sl[om] - gfirst_sl, 0.0); hs = np.empty(N); hs[om] = hold_sl
F["u_hold_mean_sl"] = ucum_excl(hs) / np.maximum(u_trips_full, 1)
F["u_mean_size"] = u_solin_full / np.maximum(u_nbuy_full, 1)
del u_pnl_full, u_cost_full, u_wins_full, u_solin_full, u_nbuy_full, hs, tp, tc, cpos, cbuy, cnet, cin, tko
# cohorts (lists built 10-23 from earlier runs; INFERRED-causal for the test day)
def wl(path):
    d = json.load(open(path)); return d if isinstance(d, list) else [x["u"] if isinstance(x, dict) else x for x in d]
cw = set(wl("/home/moiz/sniper/ops/overnight/dip/drop_cw.json")); pros = set(wl("/home/moiz/sniper/ops/overnight/dipshadow/pros53.json"))
snip = {x["w"] for x in json.load(open("/home/moiz/sniper/ops/snipers/candidates.json"))}
cen = {x["u"]: x for x in json.load(open("/home/moiz/sniper/ops/overnight/census/wallets.json"))}
def uflag(S):
    f = np.zeros(NU, bool)
    for u in S:
        i = uid.get(u)
        if i is not None: f[i] = True
    return f
is_cw = uflag(cw); is_pro = uflag(pros); is_snip = uflag(snip); cen_tot = np.zeros(NU, np.float32); cen_win = np.zeros(NU, np.float32)
for u, x in cen.items():
    i = uid.get(u)
    if i is not None: cen_tot[i] = x["tot"]; cen_win[i] = x["win"]
F["u_cw541"] = is_cw[us].astype(np.float32); F["u_pro53"] = is_pro[us].astype(np.float32); F["u_sniper66"] = is_snip[us].astype(np.float32)
F["u_census_tot"] = cen_tot[us]; F["u_census_win"] = cen_win[us]; F["u_ntr_kk"] = u_ntr_full
F["u_is_sib"] = (us == sib).astype(np.float32)
copiers = [u for u in US if u.startswith(("4mYySb7Z", "Hj4uACn8", "2QGfyorL", "8T4XX", "6nH3j"))]
is_cop = uflag(copiers); F["u_is_copier"] = is_cop[us].astype(np.float32)
F["u_is_creator"] = (us == cu).astype(np.float32)
# creates by this user before (as creator)
cr_ok = D["cr_slot"] >= 0; ck = np.sort((D["cr_user"][cr_ok].astype(np.int64) << 32) | (D["cr_slot"][cr_ok] - S0 + 1000))
F["u_ncreates"] = (np.searchsorted(ck, (us << 32) | (sl - S0 + 1000)) - np.searchsorted(ck, us << 32)).astype(np.float32)
log("WAL")
# ------------------------------------------------------------------ TX: trigger tx shape --------------------------------------
SH = np.load(f"{SCR}/shape.npz", allow_pickle=True); sh = SH["a"]
p = np.searchsorted(sh["sigh"], sigh); p = np.minimum(p, len(sh) - 1); hit = sh["sigh"][p] == sigh
log("tx join hit rate", hit.mean())
for k in ("cup", "cul", "cu", "fee", "tip", "nsign", "ntips", "relay", "route", "ixh"):
    F["tx_" + k] = np.where(hit, sh[k][p], -1).astype(np.float32)
fl = np.where(hit, sh["flags"][p], 0).astype(np.int64)
for b, nm in ((1, "cb"), (2, "nonce"), (4, "create"), (8, "close"), (16, "routed"), (32, "extend"), (64, "v2")): F["tx_f_" + nm] = ((fl & b) > 0).astype(np.float32)
F["tx_hit"] = hit.astype(np.float32)
F["tx_prio_sol"] = (np.where(hit, sh["cup"][p].astype(np.float64) * sh["cul"][p] / 1e15, 0) + np.where(hit, sh["tip"][p] / 1e9, 0)).astype(np.float32)
F["tx_fee_per_sol"] = F["tx_prio_sol"] / np.maximum(so[kk], 0.01)
del SH, sh, p
log("TX")
# ------------------------------------------------------------------ TOK: participants before e --------------------------------
def seg_cum(x):
    c = csum(x); return (c[AR + 1] - c[seg_a]).astype(np.float32)
fbuy = fo & bu   # first row of (user, mint) that is a buy  (fo = first (user,mint) row in chain order)
F["n_cw_in"] = seg_cum(fo & is_cw[us]); F["n_pro_in"] = seg_cum(fo & is_pro[us]); F["n_snip_in"] = seg_cum(fo & is_snip[us])
good = (u_trips_full >= 20) & (u_rps_full > 0.02); F["n_good_in"] = seg_cum(fo & good)
F["n_follow_in"] = seg_cum(fo & (u_follow_full >= 3))         # wallets he followed >= 3 times before
del u_trips_full, u_rps_full, u_follow_full, u_ntr_full
sibrow = us == sib; F["sib_buys"] = seg_cum(sibrow & bu); hts = csum(np.where(sibrow, np.where(bu, tk, -tk), 0)); F["sib_open"] = ((hts[AR + 1] - hts[seg_a]) > 1e3).astype(np.float32)
F["cop_buys"] = seg_cum(is_cop[us] & bu)
# his own prior P&L on this mint (realized: sells - buys so far), slots since his last sell / buy
hn = csum(np.where(mine, np.where(bu, -so, so), 0)); F["my_net"] = (hn[AR + 1] - hn[seg_a]).astype(np.float32)
# per-segment running max of last-sell slot: use rank offset trick
lastsell = np.maximum.accumulate(np.where(mine & ~bu, sl, -1) + rank * (1 << 40)) - rank * (1 << 40)
F["my_since_sell_sl"] = np.where(lastsell >= 0, sl - lastsell, -1).astype(np.float32)
lastbuy = np.maximum.accumulate(np.where(mine & bu, sl, -1) + rank * (1 << 40)) - rank * (1 << 40)
F["my_since_buy_sl"] = np.where(lastbuy >= 0, sl - lastbuy, -1).astype(np.float32)
# his last fill price vs now
lpb = np.where(mine & bu, lp, -1e9); lpb = np.maximum.accumulate(lpb + rank * 1e6) - rank * 1e6
F["my_px_vs_last_fill"] = np.where(lpb > -1e8, np.exp(lp - lpb) - 1, 0); del lpb, lastbuy, lastsell
# creator share of supply: creator net tokens / (1.073e15 - vtok)  (tokens out of the curve)
circ = np.maximum(1.073e15 - vt, 1.0)
cnt_ = csum(np.where(us == cu, np.where(bu, tk, -tk), 0)); F["dev_share"] = ((cnt_[AR + 1] - cnt_[seg_a]) / circ).astype(np.float32)
F["circ_share"] = (circ / 1.073e15).astype(np.float32)
# biggest single buyer share (approx): max buy tokens so far / circ
mb = np.maximum.accumulate(np.where(bu, tk, 0) + rank * 1e18) - rank * 1e18; F["maxbuy_share"] = (mb / circ).astype(np.float32)
log("TOK")
# ------------------------------------------------------------------ CRE: creator / launch ----------------------------------------
# per-mint outcomes (for creator history): peak vsol, dev sold within 60 s, graduated (vsol >= 100), last bt
pk_v = np.zeros(NM); np.maximum.at(pk_v, mi, vs)
devsell_bt = np.full(NM, 0); m_ds = (us == cu) & ~bu
if m_ds.any():
    tmpb = np.full(NM, 1 << 40); np.minimum.at(tmpb, mi[m_ds], bt[m_ds]); devsell_bt = tmpb
grad = pk_v >= 100.0
cr_user_m = D["cr_user"]; cr_bt_m = D["cr_bt"]
devrug = (devsell_bt < (1 << 40)) & ((devsell_bt - cr_bt_m) <= 120)
# creator history causal: tokens by the same creator created >= 1800 s before this token's create
ok = cr_ok & (cr_user_m >= 0)
oc = np.lexsort((cr_bt_m, cr_user_m)); ocu = cr_user_m[oc]; ocb = cr_bt_m[oc]
key_c = (ocu.astype(np.int64) << 32) | ocb.astype(np.int64)
c_grad = np.r_[0.0, np.cumsum(grad[oc])]; c_rug = np.r_[0.0, np.cumsum(devrug[oc])]; c_pk = np.r_[0.0, np.cumsum(pk_v[oc])]; c_n = np.arange(NM + 1, dtype=float)
def cr_hist(mint_ids):
    u_ = cr_user_m[mint_ids].astype(np.int64); b_ = cr_bt_m[mint_ids].astype(np.int64)
    lo = np.searchsorted(key_c, u_ << 32); hi = np.searchsorted(key_c, (u_ << 32) | np.maximum(b_ - 1800, 0))
    n = hi - lo
    return n, c_grad[hi] - c_grad[lo], c_rug[hi] - c_rug[lo], (c_pk[hi] - c_pk[lo]) / np.maximum(n, 1)
allm = np.arange(NM); n_, g_, r_, p_ = cr_hist(allm)
n_[~ok] = -1
F["cr_prev"] = n_[mi].astype(np.float32); F["cr_prev_grad"] = g_[mi].astype(np.float32); F["cr_prev_rug"] = r_[mi].astype(np.float32); F["cr_prev_peakv"] = p_[mi].astype(np.float32)
F["cr_prev_gradrate"] = ((g_ + 0.1) / (np.maximum(n_, 0) + 2))[mi]
# creator wallet age on tape (first row as trader) and first create
fbu = np.full(NU, 1 << 40); np.minimum.at(fbu, us, bt); cfirst = np.full(NU, 1 << 40); np.minimum.at(cfirst, cr_user_m[ok], cr_bt_m[ok])
cr_first = np.minimum(fbu[np.maximum(cr_user_m, 0)], cfirst[np.maximum(cr_user_m, 0)])
F["cr_age_s"] = np.where(ok, cr_bt_m - cr_first, -1)[mi].astype(np.float32)
# create-slot structure per mint: dev buy sol (creator buy in create slot), n bundle buys, max bundle buy, same-slot sells
dev0 = np.zeros(NM); m0 = bu & (us == cu) & (sl == cs); np.add.at(dev0, mi[m0], so[m0]); F["dev_buy0"] = dev0[mi].astype(np.float32)
bn = np.zeros(NM); m1 = bu & (us != cu) & (sl == cs); np.add.at(bn, mi[m1], 1); F["bundle_n0"] = bn[mi].astype(np.float32)
bs = np.zeros(NM); np.add.at(bs, mi[m1], so[m1]); F["bundle_sol0"] = bs[mi].astype(np.float32)
bmx = np.zeros(NM); np.maximum.at(bmx, mi[m1], so[m1]); F["bundle_max0"] = bmx[mi].astype(np.float32)
# cohort buyers in the create slot
bcw = np.zeros(NM); np.add.at(bcw, mi[m1 & is_cw[us]], 1); F["bundle_cw0"] = bcw[mi].astype(np.float32)
# NOTE: create-slot fields are only causal once e is past the create slot; for e in the create slot they look slightly ahead (flagged)
F["in_create_slot"] = (sl == cs).astype(np.float32)
F["cashback"] = D["cashback"][mi]; F["holder"] = D["holder"][mi]; F["cfee_bps"] = D["cfee_bps"]
# metadata
CA = json.load(open(f"{SEL}/creates_all.json")); mid = {m: i for i, m in enumerate(MN)}
import re
hostv = np.zeros(NM, np.int64); HOSTS = {}; nm_len = np.zeros(NM, np.float32); sy_len = np.zeros(NM, np.float32); sy_up = np.zeros(NM, np.float32)
nm_na = np.zeros(NM, np.float32); nm_w = np.zeros(NM, np.float32); van = np.zeros(NM, np.float32); nm_dig = np.zeros(NM, np.float32); nm_eq = np.zeros(NM, np.float32)
uri_len = np.zeros(NM, np.float32); nm_low = np.zeros(NM, np.float32)
for k, v in CA.items():
    i = mid.get(k)
    if i is None: continue
    m_ = re.match(r"https?://([^/]+)", v.get("uri") or ""); h = m_.group(1) if m_ else "none"
    hostv[i] = HOSTS.setdefault(h, len(HOSTS) + 1)
    n_s = v.get("name") or ""; s_s = v.get("symbol") or ""
    nm_len[i] = len(n_s); sy_len[i] = len(s_s); sy_up[i] = float(s_s.isupper()); nm_na[i] = float(any(ord(c) > 127 for c in n_s))
    nm_w[i] = len(n_s.split()); van[i] = float(k.endswith("pump")); nm_dig[i] = float(any(c.isdigit() for c in n_s)); nm_eq[i] = float(n_s.strip().lower() == s_s.strip().lower())
    uri_len[i] = len(v.get("uri") or ""); nm_low[i] = float(n_s == n_s.lower())
F["meta_host"] = hostv[mi].astype(np.float32); F["name_len"] = nm_len[mi]; F["sym_len"] = sy_len[mi]; F["sym_upper"] = sy_up[mi]; F["name_nonascii"] = nm_na[mi]
F["name_words"] = nm_w[mi]; F["vanity_pump"] = van[mi]; F["name_digit"] = nm_dig[mi]; F["name_eq_sym"] = nm_eq[mi]; F["uri_len"] = uri_len[mi]; F["name_lower"] = nm_low[mi]
json.dump({v: k for k, v in HOSTS.items()}, open(f"{OUT}/hosts.json", "w"))
log("CRE")
# ------------------------------------------------------------------ TIM --------------------------------------------------------
F["slot_in_win"] = (sl % 4).astype(np.float32); F["dow"] = (((bt + 18000) // 86400) % 7).astype(np.float32)
F["minute"] = (((bt + 18000) % 3600) // 60).astype(np.float32)
# his activity: his buys/sells in the last 60 s / 300 s (any mint), slots since his last trade (any mint)
hrows = np.flatnonzero(mine); hb_bt = bt[hrows]; o2 = np.argsort(hb_bt, kind="stable"); hb_bt = hb_bt[o2]; hbuy = bu[hrows][o2]
cb_ = np.r_[0, np.cumsum(hbuy)]; cs_ = np.r_[0, np.cumsum(~hbuy)]
for lab, k in (("60", 60), ("300", 300)):
    lo = np.searchsorted(hb_bt, bt - k); hi = np.searchsorted(hb_bt, bt, side="left")   # strictly before this second (block clock 1 s)
    F["my_buys_" + lab] = (cb_[hi] - cb_[lo]).astype(np.float32); F["my_sells_" + lab] = (cs_[hi] - cs_[lo]).astype(np.float32)
hi = np.searchsorted(hb_bt, bt, side="left"); F["my_gap_s"] = np.where(hi > 0, bt - hb_bt[np.maximum(hi - 1, 0)], 9999).astype(np.float32)
# open positions count (approx): cumulative distinct mints bought minus closed, from his own trips (cl on his rows)
hcl = cl[hrows][o2]; hfo = fo[hrows][o2] & hbuy
co_ = np.r_[0, np.cumsum(hfo.astype(int) - hcl.astype(int))]; F["my_open_n"] = co_[hi].astype(np.float32)
# sib activity in the last 60 s
srows = np.flatnonzero(sibrow); sb_bt = np.sort(bt[srows]); F["sib_trades_60"] = (np.searchsorted(sb_bt, bt, side="left") - np.searchsorted(sb_bt, bt - 60)).astype(np.float32)
log("TIM")
# ------------------------------------------------------------------ forward returns (market) ------------------------------------
def lp_at_or_before(k):
    q = np.searchsorted(K, (mi << 32) | (sl + k - S0), side="right") - 1
    return lp[q]
def lp_at_or_before_kk(k):
    q = np.searchsorted(K, (mi[kk] << 32) | (sl[kk] + k - S0), side="right") - 1
    return lp[q]
lp1 = lp_at_or_before_kk(1); lpk = lp[kk]
fw = {}
for k in (5, 24, 94, 160): fw[f"f{k}"] = (np.exp(lp_at_or_before_kk(k) - lpk) - 1).astype(np.float32)
for k in (24, 94, 160): fw[f"g{k}"] = (np.exp(lp_at_or_before_kk(k) - lp1) - 1).astype(np.float32)
# ------------------------------------------------------------------ save ---------------------------------------------
out = dict(F); out.update(fw)
out.update(row=kk, y=y[kk], ysib=ysib[kk], samp=samp[kk], mint=mi[kk], slot=sl[kk], idx=ix[kk], bt=bt[kk], user=us[kk], nxt_row=nxt_row[kk], nxt_sib=nxt_sib[kk],
           sigh=sigh[kk], lp=lp[kk].astype(np.float32), vt=vt[kk], seg_a=seg_a[kk])
np.savez(f"{OUT}/U2.npz", **out)
log("saved", len(kk), "features", len(F))
