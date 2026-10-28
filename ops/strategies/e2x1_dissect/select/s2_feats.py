#!/usr/bin/env python3
"""SELECT s2: per E2x1 buy, causal context features (rows strictly before his buy row on that mint) + outcome.
Outcome: lot P&L by TRIP (flat -> flat on the mint): each buy gets tokens * (that trip's avg sell px) - sol; tokens sold beyond
bought are not credited; a trip never closed in the tape values its unsold tokens at 0 (flag unsold)."""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"])
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9
tk = D["tok"].astype(np.float64); vs = D["vsol"] / 1e9; vt = D["vtok"].astype(np.float64); mi = D["mint"]; bt = D["bt"].astype(np.int64); us = D["user"].astype(np.int64)
px = vs / np.maximum(vt, 1) * 1e6          # SOL per 1e6 raw units (relative only)
mine = np.flatnonzero(us == w)
rows = []
for m in np.unique(mi[mine]):
    a, e = span(D, m)
    s_ = sl[a:e]; u_ = us[a:e]; b_ = bu[a:e]; o_ = so[a:e]; k_ = tk[a:e]; p_ = px[a:e]; v_ = vs[a:e]; t_ = bt[a:e]
    if D["cr_slot"][m] < 0 or not D["solq"][m]: continue
    cs = int(D["cr_slot"][m]); cu = int(D["cr_user"][m]); cbt = int(D["cr_bt"][m])
    p0 = 30.0 / 1.073e15 * 1e6 * 1e9 / 1e9   # px at creation (vsol 30, vtok 1.073e15)
    my = u_ == w
    sb = o_[my & b_].sum(); ss = o_[my & ~b_].sum(); tb_ = k_[my & b_].sum(); ts_ = k_[my & ~b_].sum()
    avg_sell = ss / max(ts_, tb_) if ts_ > 0 else 0.0     # tokens sold beyond bought (pre-window buys) not credited; unsold valued 0
    unsold = 1 - ts_ / tb_ if tb_ > 0 else 0
    # trips: walk his rows; trip id per buy row; per trip avg sell px over max(sold, bought) tokens
    trip_of = {}; trips = []; held = 0.0; cur = None
    for q in np.flatnonzero(my):
        if b_[q]:
            if cur is None: cur = [0.0, 0.0, 0.0]; trips.append(cur)      # bought tok, sold tok, sold sol
            cur[0] += k_[q]; held += k_[q]; trip_of[q] = len(trips) - 1
        elif cur is not None:
            cur[1] += k_[q]; cur[2] += o_[q]; held -= k_[q]
            if held <= cur[0] * 1e-4: held = 0.0; cur = None
    topen = [t[1] < t[0] * 0.99 for t in trips]
    # unclosed trips (mostly graduated tokens sold later on PumpSwap, outside this tape): mark the unsold tokens at the LAST curve px
    # on the mint (net 1.25 % fee); recon's exact lots show these are mostly big winners (D0+D1: 34 PumpSwap sells, +60 SOL vs value 0)
    lastpx = v_[-1] / max(vt[a:e][-1], 1) * 0.9875
    tpx = [(t[2] + (max(t[0] - t[1], 0) * lastpx if o else 0.0)) / max(t[0], t[1]) for t, o in zip(trips, topen)]
    pk = np.maximum.accumulate(p_)
    nb_mine = 0
    last_sell_my = -1
    for r in np.flatnonzero(my & b_):
        R = a + r
        pre = slice(0, r)                       # strictly before his row
        sp = s_[r]
        def px_at(slot_lim):                    # px after last row with slot < slot_lim (or creation px)
            q = np.searchsorted(s_[:r], slot_lim) - 1
            return p_[q] if q >= 0 else p0
        pnow = p_[r - 1] if r > 0 else p0
        f = dict(row=int(R), mint=int(m), slot=int(sp), idx=int(ix[R]), bt=int(t_[r]), sol=float(o_[r]), tok=float(k_[r]),
                 add=nb_mine, age_s=int(t_[r] - cbt), age_sl=int(sp - cs), vsol_pre=float(v_[r - 1]) if r > 0 else 30.0,
                 vsol_after=float(v_[r]))
        nb_mine += 1
        for lab, k in (("1s", 5), ("5s", 24), ("30s", 141), ("120s", 566)):
            f["ret_" + lab] = pnow / px_at(sp - k) - 1
        f["dd_peak"] = pnow / max(pk[r - 1] if r > 0 else p0, p0) - 1
        f["mult_create"] = pnow / p0
        # flows windows (rows strictly before)
        for lab, k in (("cur", 0), ("1s", 5), ("5s", 24), ("30s", 141)):
            lo = np.searchsorted(s_[:r], sp - k)
            ww = slice(lo, r); ob = ~my[ww]
            bb = b_[ww] & ob; ssx = ~b_[ww] & ob
            f["nb_" + lab] = int(bb.sum()); f["ns_" + lab] = int(ssx.sum())
            f["solin_" + lab] = float(o_[ww][bb].sum()); f["solout_" + lab] = float(o_[ww][ssx].sum())
            f["ub_" + lab] = len(set(u_[ww][bb].tolist()))
            f["maxbuy_" + lab] = float(o_[ww][bb].max()) if bb.any() else 0.0
            f["maxsell_" + lab] = float(o_[ww][ssx].max()) if ssx.any() else 0.0
        # trigger candidates: biggest single-trade price impact (outside rows) in slots [sp-3, sp], rows before his
        lo3 = np.searchsorted(s_[:r], sp - 3)
        imp = np.array([p_[q] / (p_[q - 1] if q > 0 else p0) - 1 for q in range(lo3, r)]) if r > lo3 else np.zeros(0)
        oo = ~my[lo3:r]
        si = np.where(oo & ~b_[lo3:r], imp, 0.0); bi = np.where(oo & b_[lo3:r], imp, 0.0)
        f["trg_sell_imp"] = float(si.min()) if len(si) else 0.0
        f["trg_sell_dsl"] = int(sp - s_[lo3 + int(si.argmin())]) if len(si) and si.min() < 0 else -1
        f["trg_sell_sol"] = float(o_[lo3 + int(si.argmin())]) if len(si) and si.min() < 0 else 0.0
        f["trg_sell_cr"] = bool(u_[lo3 + int(si.argmin())] == cu) if len(si) and si.min() < 0 else False
        f["trg_buy_imp"] = float(bi.max()) if len(bi) else 0.0
        f["trg_buy_dsl"] = int(sp - s_[lo3 + int(bi.argmax())]) if len(bi) and bi.max() > 0 else -1
        f["trg_buy_sol"] = float(o_[lo3 + int(bi.argmax())]) if len(bi) and bi.max() > 0 else 0.0
        f["trg_buy_cr"] = bool(u_[lo3 + int(bi.argmax())] == cu) if len(bi) and bi.max() > 0 else False
        lo10 = np.searchsorted(s_[:r], sp - 10)
        f["dd10"] = pnow / max(p_[lo10:r].max() if r > lo10 else p0, (p_[lo10 - 1] if lo10 > 0 else p0)) - 1
        f["up10"] = pnow / min(p_[lo10:r].min() if r > lo10 else p0, (p_[lo10 - 1] if lo10 > 0 else p0)) - 1
        f["last_dsl"] = int(sp - s_[r - 1]) if r > 0 else -1
        # previous trade
        if r > 0:
            q = r - 1
            f.update(prev_buy=bool(b_[q]), prev_sol=float(o_[q]), prev_self=bool(my[q]), prev_dslot=int(sp - s_[q]),
                     prev_didx=int(ix[R] - ix[a + q]) if s_[q] == sp else -1, prev_user=int(u_[q]), prev_creator=bool(u_[q] == cu))
        else:
            f.update(prev_buy=False, prev_sol=0.0, prev_self=False, prev_dslot=-1, prev_didx=-1, prev_user=-1, prev_creator=False)
        # totals so far
        f["ntr"] = int(r); f["nusers"] = len(set(u_[:r].tolist()))
        cr_b = (u_[:r] == cu) & b_[:r]; cr_s = (u_[:r] == cu) & ~b_[:r]
        f["dev_buy_sol"] = float(o_[:r][cr_b].sum()); f["dev_sold"] = bool(cr_s.any())
        f["bundle_n"] = len(set(u_[:r][(s_[:r] == cs) & b_[:r]].tolist()) - {cu}); f["bundle_sol"] = float(o_[:r][(s_[:r] == cs) & b_[:r] & (u_[:r] != cu)].sum())
        f["tot_in"] = float(o_[:r][b_[:r]].sum()); f["tot_out"] = float(o_[:r][~b_[:r]].sum())
        # holder concentration: top-5 net token balance share of circulating (rows before)
        bal = collections.defaultdict(float)
        for uu, bb2, kk in zip(u_[:r].tolist(), b_[:r].tolist(), k_[:r].tolist()): bal[uu] += kk if bb2 else -kk
        vals = sorted((x for x in bal.values() if x > 0), reverse=True); tot = sum(vals)
        f["top5_share"] = sum(vals[:5]) / tot if tot > 0 else 0; f["holders"] = len(vals)
        f["dev_bal_share"] = max(bal.get(cu, 0), 0) / tot if tot > 0 else 0
        # outcome
        f["lot_pnl"] = float(k_[r] * tpx[trip_of[r]] - o_[r]); f["unsold"] = float(topen[trip_of[r]]); f["trip"] = trip_of[r]
        f["mint_pnl"] = float(ss - sb)
        # market forward returns from his fill price (px after his row) at +1/+5/+30 s (last row before slot+k)
        pf = p_[r]
        for lab, k in (("1s", 5), ("5s", 24), ("30s", 141)):
            q = np.searchsorted(s_, sp + k) - 1
            f["fwd_" + lab] = p_[q] / pf - 1
        # his next sell on this mint
        ns = np.flatnonzero(my[r + 1:] & ~b_[r + 1:])
        f["hold_s"] = int(t_[r + 1 + ns[0]] - t_[r]) if len(ns) else -1
        f["hold_sl"] = int(s_[r + 1 + ns[0]] - sp) if len(ns) else -1
        rows.append(f)
pickle.dump(rows, open(f"{OUT}/buys.pkl", "wb"))
print(len(rows))
