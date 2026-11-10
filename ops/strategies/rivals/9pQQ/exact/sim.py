#!/usr/bin/env python3
"""The RECONSTRUCTED 9pQQ bot, free-running on the tape (its own state is the replica's, not 9pQQ's).
Decision function = learned buy score (g1_b_rt_nog) and sell score (g1_s_rt_nog), trained on 10-28+10-30, plus its proven hard rules:
never mayhem, age >= 9 slots, curve < 112 SOL, one 0.7 SOL buy + one full sell, re-entry >= 2 slots after its sell, no sell before
buy+2 slots, time cap CAP s.  Buy when score_b >= TB on an outside trade while flat; sell when score_s >= TS while holding.
Scoring vs 9pQQ: buy match = same mint and its real buy within +-2 slots of ours; sell match (matched trips) = |slot diff| <= 1.
P&L: rlib9 paper round trips with 9pQQ's own trades removed from the curve, at (a) its speed: +45 ms after the trigger, 0.7 SOL, 1.46
mSOL/trip, (b) our speed: +70 ms, 0.55 SOL, 4.5 mSOL/trip, and (c) (b) with -20 % followers.
usage: sim.py RUN TB_Q TS [CAP]    TB_Q = buy threshold as a quantile of buy scores on flat rows (e.g. 0.997); TS = sell prob threshold"""
import sys, json, pickle, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import xlib as X, tlib9 as L, rlib9 as R, fgb
run = sys.argv[1]; TBQ = float(sys.argv[2]); TS = float(sys.argv[3]); CAP = float(sys.argv[4]) if len(sys.argv) > 4 else 600.0
MB = fgb.Flat(pickle.load(open(f"{X.XOUT}/g1_b_rt_nog.pkl", "rb"))); MS = fgb.Flat(pickle.load(open(f"{X.XOUT}/g1_s_rt_nog.pkl", "rb")))
z = np.load(f"{X.XOUT}/dm_{run}.npz"); q = np.load(f"{X.XOUT}/rt_{run}.npz")
col = lambda k: (z[k] if k in z.files else q[k]).astype(np.float64)
DYN_B = {"k_done", "since_own_sell", "since_own_buy", "v_vs_ownbuy", "v_vs_ownsell", "last_trip_ret"}
DYN_S = {"k_done", "since_own_buy", "v_vs_ownbuy", "peak_since_buy", "trough_since_buy", "dd_peak_buy", "sg_hold", "bsol_hold", "ssol_hold", "nb_hold", "ns_hold"}
def static_bins(M, dyn):
    B = np.zeros((len(z["s"]), len(M.names)), np.int16)
    for j, k in enumerate(M.names):
        if k not in dyn: B[:, j] = M.bin_col(j, col(k))
    return B
BB = static_bins(MB, DYN_B); BS = static_bins(MS, DYN_S)
S = z["s"]; BT = None; V = col("vsol"); SIDE = col("side"); SIZE = col("size"); AGE = col("age"); MAY = col("may"); ROW = z["row"]; MM = z["m"]
SG = SIDE * SIZE; BSOL = np.where(SIDE > 0, SIZE, 0.0); SSOL = np.where(SIDE < 0, SIZE, 0.0); NB = (SIDE > 0) * 1.0; NS = (SIDE < 0) * 1.0
t = X.load(run); s0, bsz = R.blocksizes(run); wid = t.user_ix[L.W]; BTt = t.bt
ok_buy = (MAY == 0) & (AGE >= 9) & (V < 112)
# buy threshold from the score distribution on flat rows with the 'never traded' own state
nb_idx = np.where(ok_buy)[0]
def fill_b(B, rows, st):
    sl = S[rows].astype(np.float64); v = V[rows]
    vals = {"k_done": np.full(len(rows), st["k"], float),
            "since_own_sell": sl - st["s_ls"] if st["s_ls"] is not None else np.full(len(rows), 99999.0),
            "since_own_buy": sl - st["s_lb"] if st["s_lb"] is not None else np.full(len(rows), 99999.0),
            "v_vs_ownbuy": v / st["v_lb"] - 1 if st["v_lb"] else np.full(len(rows), np.nan),
            "v_vs_ownsell": v / st["v_ls"] - 1 if st["v_ls"] else np.full(len(rows), np.nan),
            "last_trip_ret": np.full(len(rows), st["ltr"] if st["ltr"] is not None else np.nan)}
    for j, k in enumerate(MB.names):
        if k in vals: B[:, j] = MB.bin_col(j, vals[k])
    return B
def fill_s(B, rows, st, e):
    sl = S[rows].astype(np.float64); v = V[rows]
    pk = np.maximum(np.maximum.accumulate(v), st["v_lb"]); tr = np.minimum(np.minimum.accumulate(v), st["v_lb"])
    vals = {"k_done": np.full(len(rows), st["k"], float), "since_own_buy": sl - st["s_lb"], "v_vs_ownbuy": v / st["v_lb"] - 1,
            "peak_since_buy": pk, "trough_since_buy": tr, "dd_peak_buy": v / pk - 1}
    for k, a in (("sg_hold", SG), ("bsol_hold", BSOL), ("ssol_hold", SSOL), ("nb_hold", NB), ("ns_hold", NS)):
        vals[k] = np.cumsum(a[rows])
    for j, k in enumerate(MS.names):
        if k in vals: B[:, j] = MS.bin_col(j, vals[k])
    return B
never = dict(k=0, s_ls=None, s_lb=None, v_lb=None, v_ls=None, ltr=None)
samp = nb_idx[::7]
sc0 = MB.margin(fill_b(BB[samp].copy(), samp, never))
TB = float(np.quantile(sc0, TBQ)); TSm = float(np.log(TS / (1 - TS)))
mst = np.searchsorted(MM, np.arange(MM.max() + 2))           # dm rows per mint (dm sorted by tape row => by mint)
trips = []
CH = 512
for mi in np.unique(MM[nb_idx]):
    a0, a1 = mst[mi], mst[mi + 1]
    st = dict(never); j = a0; Mn = None
    while j < a1:
        # ---- flat: search the next buy
        found = None
        while j < a1 and found is None:
            rows = np.arange(j, min(a1, j + CH)); rows = rows[ok_buy[rows]]
            if st["s_ls"] is not None: rows = rows[S[rows] >= st["s_ls"] + 2]
            if len(rows):
                sc = MB.margin(fill_b(BB[rows].copy(), rows, st)); h = np.where(sc >= TB)[0]
                if len(h): found = rows[h[0]]
            j = min(a1, j + CH) if found is None else found + 1
        if found is None: break
        e = found; sb = int(S[e])
        if Mn is None: Mn = R.Mint(t, int(mi), s0, bsz, wid)
        st.update(s_lb=sb, v_lb=float(V[e]) + 0.69, k=st["k"])
        # ---- hold: search the sell
        j = e + 1; sold = None; capped = False
        bt_b = int(BTt[ROW[e]])
        while j < a1 and sold is None:
            rows = np.arange(j, min(a1, j + CH))
            over = np.where(BTt[ROW[rows]] - bt_b >= CAP)[0]
            if len(over): rows_c = rows[:over[0]]
            else: rows_c = rows
            cand = rows_c[S[rows_c] >= sb + 2]
            if len(cand):
                allr = np.arange(e + 1, cand[-1] + 1)               # hold flows need every row since the buy
                B = fill_s(BS[allr].copy(), allr, st, e); sc = MS.margin(B[-len(cand):] if False else B[np.searchsorted(allr, cand)])
                h = np.where(sc >= TSm)[0]
                if len(h): sold = cand[h[0]]; break
            if len(over): capped = True; break
            j = min(a1, j + CH)
        trip = dict(m=int(mi), eb=int(ROW[e]), sb=sb)
        if sold is not None:
            trip.update(es=int(ROW[sold]), ss=int(S[sold]), cap=False); ve = float(V[sold]); se = int(S[sold]); j = sold + 1
        else:
            trip.update(es=None, ss=None, cap=True, bt_b=bt_b); ve = None; se = None; j = a1 if not capped else (rows[over[0]] if len(over) else a1)
            # after a capped exit continue from the first row after cap time
            se = int(S[j - 1]) if j - 1 > e else sb + 1; ve = float(V[j - 1]) if j - 1 > e else float(V[e])
        st = dict(k=st["k"] + 1, s_ls=se, v_ls=ve, s_lb=sb, v_lb=st["v_lb"], ltr=(ve / st["v_lb"]) ** 2 - 1)
        trips.append(trip)
# ---------- P&L and matching
def pnl(tr, delta, size, cost, fol=0.0):
    tot = []
    cache = {}
    for x in tr:
        Mn = cache.get(x["m"]) or R.Mint(t, x["m"], s0, bsz, wid); cache[x["m"]] = Mn
        ib = x["eb"] - t.mstart[x["m"]]; tin = Mn.CC[ib] + delta
        if x["cap"]: tout = tin + CAP * 1000.0
        else: tout = Mn.CC[x["es"] - t.mstart[x["m"]]] + delta
        tot.append(R.trip(Mn, tin, tout, size=size, drop9=True, fol=fol, cost=cost))
    return np.array(tot) / 1e9
ob = t.ob; os_ = t.os
hb = {}
for k in ob: hb.setdefault(int(t.m[k]), []).append(int(t.s[k]))
hs = {}
for k in os_: hs.setdefault(int(t.m[k]), []).append(int(t.s[k]))
matched = 0; sell_hit = 0; sell_d = []; used = set()
for x in trips:
    c = [s_ for s_ in hb.get(x["m"], []) if abs(s_ - x["sb"]) <= 2 and (x["m"], s_) not in used]
    if c:
        matched += 1; used.add((x["m"], c[0])); x["match"] = True
        # its sell after that buy
        ss = [s_ for s_ in hs.get(x["m"], []) if s_ >= c[0]]
        if ss and x["ss"] is not None:
            sell_d.append(x["ss"] - ss[0]); sell_hit += abs(x["ss"] - ss[0]) <= 1
hrs = (t.bt.max() - t.bt.min()) / 3600
his = [x for x in pickle.load(open(f"{L.OUT}/trips_{run}.pkl", "rb")) if x.get("net") is not None]
P1 = pnl(trips, 45, 0.7e9, 1.46e6); P2 = pnl(trips, 70, 0.55e9, 4.5e6); P3 = pnl(trips, 70, 0.55e9, 4.5e6, fol=0.2)
sd = np.array(sell_d) if sell_d else np.array([0])
out = dict(run=run, day=X.DAY[run], TBQ=TBQ, TS=TS, CAP=CAP, hours=round(hrs, 2), his_buys=len(ob), replica_buys=len(trips),
           buy_precision=round(matched / max(1, len(trips)), 4), buy_recall=round(matched / max(1, len(ob)), 4),
           sell_hit_pm1_of_matched=round(sell_hit / max(1, len(sell_d)), 4), sell_slot_diff_p=np.percentile(sd, [10, 25, 50, 75, 90]).tolist(),
           capped=sum(1 for x in trips if x["cap"]),
           pnl_his_speed=dict(net=round(P1.sum(), 2), per_day=round(P1.sum() / hrs * 24, 1), msol=round(1000 * P1.mean(), 2), wo_top5=round(np.sort(P1)[:-5].sum(), 2)),
           pnl_our_speed=dict(net=round(P2.sum(), 2), per_day=round(P2.sum() / hrs * 24, 1), msol=round(1000 * P2.mean(), 2), wo_top5=round(np.sort(P2)[:-5].sum(), 2)),
           pnl_our_speed_fol20=dict(net=round(P3.sum(), 2), per_day=round(P3.sum() / hrs * 24, 1)),
           his_real_net=round(sum(x["net"] for x in his) / 1e9, 2), his_real_per_day=round(sum(x["net"] for x in his) / 1e9 / hrs * 24, 1))
print(json.dumps(out), flush=True)
os.makedirs(f"{X.XOUT}/sim", exist_ok=True)
json.dump(dict(out, trips=trips), open(f"{X.XOUT}/sim/sim_{X.DAY[run]}_{TBQ}_{TS}.json", "w"), default=int)
