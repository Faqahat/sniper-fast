#!/usr/bin/env python3
"""HAQQ DISSECT / pos step 1 (read-only, offline): haqq's buys, FIFO lots, pro-rata lots and trips on the WHOLE tape
(dv8/tab, 10-22 03:07 -> 10-28 01:12 PKT), with causal context before every buy.

Trip = first buy -> balance back to <= 0.5% of the trip's peak (flat).  k-th trip on a token = order of trips on that mint.
Lot accounting (both MEASURED from the tape):
  FIFO    : each sell consumes the oldest open lot first;
  pro-rata: each sell takes tokens from every open lot in proportion to its remaining tokens (= average-cost view).
Tx costs: per landed tx (unique slot,idx of his rows) = fee + tips from haqq_raw.jsonl where present (10-25 19:20 -> 10-28 00:41),
  else 0.396 mSOL/tx (MEASURED mean 0.392 landed + 8.8% failed x 0.042). Failed-tx fees spread per landed tx (same 0.004).
Context per buy (only rows BEFORE the buy in chain order -> causal):
  biggest outside single-sell drop in the last 5 slots (drop, SOL, slots before, dumper = dev/bundler/early/other),
  outside dumps (>=5% drop) since his previous buy / since trip start / since create, outside buy & sell SOL in the last 3 slots
  and since his previous buy, distinct outside wallets since his previous buy, price vs his previous buy / vs avg cost of the open
  position, the open position's unrealized return (exact curve sell of his open tokens at the pre-buy state, net of fee),
  price vs 10-slot high, price change over the last 10 slots, age, curve SOL, mayhem flag (create).
Out: /home/moiz/sniper-data/haqq_dissect/pos/p1.pkl"""
import json, time, collections, pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/pos"
TXC_DEF = 0.000396; FAILSH = 0.088 * 0.000042


def main():
    t0 = time.time()
    ids, idm = L.ids_map(); h = idm[L.HAQQ]
    our = set(idm[w] for w in L.WAL.values() if w in idm)
    T = np.load(f"{L.TAB}/trades.npy")
    mh = (T["user"] == h) | (T["signer"] == h)
    mints = np.unique(T["mint"][mh])
    sub = T[np.isin(T["mint"], mints)]; del T
    o = np.argsort(sub["mint"], kind="stable"); sub = sub[o]
    print(f"haqq rows {mh.sum():,}, mints {len(mints):,}, rows of those mints {len(sub):,} ({time.time() - t0:.0f}s)", flush=True)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    CODES = pickle.load(open(f"{OUT}/codes.pkl", "rb"))     # p1b: every haqq tx in the raw recordings (code = CU price mod 1000)
    cost = {k: v[1] for k, v in CODES.items() if k[0] != "F"}
    code = {k: v[0] for k, v in CODES.items() if k[0] != "F"}
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    um, st_ = np.unique(sub["mint"], return_index=True); en_ = np.append(st_[1:], len(sub))
    ccg = L.cc(sub["slot"].astype(np.int64), sub["idx"].astype(np.int64))
    BUYS, SELLS, LOTS, TRIPS = [], [], [], []
    MATCH = [0.0, 0.0]
    nm_done = 0
    for mi, a, e in zip(um.tolist(), st_.tolist(), en_.tolist()):
        mint = ids[mi]; c = CR.get(mint) or {}
        cs = int(c["slot"]) if c.get("slot") is not None else None
        cr = idm.get(c.get("creator"), -2); mayhem = bool(c.get("mayhem"))
        sl = sub["slot"][a:e].astype(np.int64); ix = sub["idx"][a:e].astype(np.int64)
        us = sub["user"][a:e].astype(np.int64); sg = sub["signer"][a:e].astype(np.int64); bu = sub["buy"][a:e].astype(bool)
        so = sub["sol"][a:e] / 1e9; tk = sub["tok"][a:e].astype(np.float64); vs = sub["vsol"][a:e] / 1e9; vt = sub["vtok"][a:e].astype(np.float64)
        bt = sub["bt"][a:e].astype(np.int64); fee = (sub["fee_bps"][a:e].astype(np.float64) + sub["cfee_bps"][a:e]) / 1e4
        cca = ccg[a:e]; n = e - a
        px = vs / np.maximum(vt, 1)
        v_c = float(c.get("vsol") or 30e9) / 1e9; t_c = float(c.get("vtok") or 1.073e15)
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        vsp = np.empty(n); vsp[0] = v_c; vsp[1:] = vs[:-1]
        vtp = np.empty(n); vtp[0] = t_c; vtp[1:] = vt[:-1]
        with np.errstate(divide="ignore", invalid="ignore"): drop = np.where(~bu, 1 - px / pxp, 0.0)
        isH = (us == h) | (sg == h); outside = ~isH
        isdump = outside & ~bu & (drop >= 0.05)
        cdump = np.cumsum(isdump)
        cbo = np.cumsum(np.where(bu & outside, so, 0.0)); cso = np.cumsum(np.where(~bu & outside, so, 0.0))
        bund = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
        early = set(us[(sl <= cs + 10) & bu].tolist()) if cs is not None else set()
        q = []                # open lots (dicts) in FIFO order
        cq = []               # open lots for code-matched accounting
        bal = 0.0; trip = None; ktrip = 0; last_hbuy = None
        hk = np.flatnonzero(isH).tolist()
        for k in hk:
            key = (int(sl[k]), int(ix[k]))
            if bu[k]:
                gc = so[k] * (1 + fee[k])
                new_trip = trip is None or bal <= 0
                if new_trip:
                    ktrip += 1
                    prev = TRIPS[-1] if (TRIPS and TRIPS[-1]["mint"] == mint) else None
                    trip = dict(mint=mint, mi=mi, k=ktrip, slot0=int(sl[k]), bt0=int(bt[k]), cc0=float(cca[k]), cost=0.0, out=0.0, nb=0, ns=0,
                                peak=0.0, close_slot=None, close_bt=None, close_cc=None, lots=[], txs=set(), mayhem=mayhem, cs=cs,
                                prev_net=(prev["out"] - prev["cost"]) if prev else None, prev_close_cc=prev["close_cc"] if prev else None,
                                gap=False)
                    TRIPS.append(trip); last_hbuy = None
                # ---- context (rows < k)
                lo5 = int(np.searchsorted(sl, sl[k] - 5)); lo3 = int(np.searchsorted(sl, sl[k] - 3)); lo10 = int(np.searchsorted(sl, sl[k] - 10))
                cand = [j for j in range(lo5, k) if isdump[j] or (outside[j] and not bu[j])]
                dj = max(cand, key=lambda j: drop[j]) if cand else None
                pb = last_hbuy  # previous buy row in this trip
                ps = trip["slot0"]
                open_tok = sum(l["left"] for l in q); open_cost = sum(l["cost"] * l["left"] / l["tok"] for l in q)
                if open_tok > 0:
                    K = vsp[k] * vtp[k]; val = (vsp[k] - K / (vtp[k] + open_tok)) * (1 - fee[k])
                    unreal = val / open_cost - 1 if open_cost > 0 else None
                else:
                    unreal = None
                avg_px = open_cost / open_tok if open_tok > 0 else None
                prev_lot = LOTS[trip["lots"][-1]] if trip["lots"] else None
                rng_prev = slice(pb + 1, k) if pb is not None else slice(k, k)
                ow = us[rng_prev][outside[rng_prev]]
                hs_sold = bool((isH[rng_prev] & ~bu[rng_prev]).any()) if pb is not None else False
                mx10 = float(px[lo10:k].max()) if k > lo10 else pxp[k]
                px10 = pxp[lo10] if lo10 < k else pxp[k]
                dumps_since_prev = int(cdump[k - 1] - cdump[pb]) if (pb is not None and k > 0) else None
                trip_start_row = trip.get("row0", k)
                B = dict(mint=mint, mi=mi, row=a + k, k=k, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cc=float(cca[k]), size=gc,
                         tok=float(tk[k]), pre_px=float(pxp[k]), vsol_pre=float(vsp[k]), age=int(sl[k] - cs) if cs is not None else None,
                         mayhem=mayhem, trip_ix=len(TRIPS) - 1, ktrip=ktrip, kbuy=trip["nb"] + 1,
                         dt_prev_ms=float(cca[k] - cca[pb]) if pb is not None else None, dt_prev_slots=int(sl[k] - sl[pb]) if pb is not None else None,
                         dt_start_ms=float(cca[k] - trip["cc0"]), px_vs_prev=float(pxp[k] / pxp[pb] - 1) if pb is not None else None,
                         px_vs_prevfill=None, px_vs_avg=float(pxp[k] / avg_px - 1) if avg_px else None, unreal=unreal, open_tok=open_tok,
                         open_cost=open_cost, prev_lot_open=(prev_lot["left"] > 0.5) if prev_lot else None,
                         n_open_lots=len(q), sold_since_prev=hs_sold, nw_since_prev=len(set(ow.tolist())), ntr_since_prev=int(len(ow)),
                         dumps_since_prev=dumps_since_prev, dumps_before=int(cdump[k - 1]) if k > 0 else 0,
                         dumps_in_trip=int(cdump[k - 1] - cdump[trip_start_row - 1]) if trip_start_row > 0 and k > 0 else (int(cdump[k - 1]) if k > 0 else 0),
                         bo3=float(cbo[k - 1] - (cbo[lo3 - 1] if lo3 > 0 else 0)) if k > 0 else 0.0,
                         so3=float(cso[k - 1] - (cso[lo3 - 1] if lo3 > 0 else 0)) if k > 0 else 0.0,
                         bo_prev=float(cbo[k - 1] - cbo[pb]) if pb is not None else None, so_prev=float(cso[k - 1] - cso[pb]) if pb is not None else None,
                         dd10=float(1 - pxp[k] / mx10) if mx10 > 0 else 0.0, ch10=float(pxp[k] / px10 - 1) if px10 > 0 else 0.0,
                         hq_trades_before=int(isH[:k].sum()), prev_trip_net=trip["prev_net"] if new_trip else None, new_trip=new_trip)
                if dj is not None:
                    seller = us[dj]
                    B.update(d_drop=float(drop[dj]), d_sol=float(so[dj]), d_slots=int(sl[k] - sl[dj]), d_ms=float(cca[k] - cca[dj]),
                             d_type=("dev" if seller == cr else "bundler" if seller in bund else "early" if seller in early else "other"),
                             d_after_prev=(pb is not None and dj > pb), d_nbuy=int((bu[dj + 1:k] & outside[dj + 1:k]).sum()), d_row=a + dj,
                             d_slot=int(sl[dj]), d_idx=int(ix[dj]))
                else:
                    B.update(d_drop=0.0, d_sol=0.0, d_slots=None, d_ms=None, d_type=None, d_after_prev=False, d_nbuy=None, d_row=None, d_slot=None, d_idx=None)
                if new_trip: trip["row0"] = k
                BUYS.append(B)
                lot = dict(b=len(BUYS) - 1, mint=mint, slot=int(sl[k]), cc=float(cca[k]), cost=gc, tok=float(tk[k]), left=float(tk[k]), pleft=float(tk[k]),
                           out=0.0, pout=0.0, close_cc=None, pclose_cc=None, nsell=0, txc=cost.get(key, TXC_DEF) + FAILSH, sell_txc=0.0, kbuy=trip["nb"] + 1,
                           trip_ix=len(TRIPS) - 1, code=code.get(key), cleft=float(tk[k]), cout=0.0, csell_txc=0.0, cclose_cc=None)
                LOTS.append(lot); q.append(lot); cq.append(lot)
                trip["cost"] += gc; trip["nb"] += 1; trip["lots"].append(len(LOTS) - 1); trip["txs"].add(key)
                bal += tk[k]; trip["peak"] = max(trip["peak"], bal); last_hbuy = k
            else:
                gross = so[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                stc = cost.get(key, TXC_DEF) + FAILSH
                if trip is not None:
                    trip["out"] += gross; trip["ns"] += 1; trip["txs"].add(key)
                    # pro-rata over open lots
                    ptot = sum(LOTS[li]["pleft"] for li in trip["lots"] if LOTS[li]["pleft"] > 0.5)
                    if ptot > 0:
                        frac = min(tot / ptot, 1.0)
                        for li in trip["lots"]:
                            l = LOTS[li]
                            if l["pleft"] > 0.5:
                                tkn = l["pleft"] * frac; l["pout"] += gross * tkn / tot; l["pleft"] -= tkn
                                if l["pleft"] <= 0.5 or frac >= 0.999: l["pleft"] = 0.0; l["pclose_cc"] = float(cca[k])
                    SELLS.append(dict(mint=mint, trip_ix=len(TRIPS) - 1, slot=int(sl[k]), cc=float(cca[k]), sol=gross, tok=tot, txc=stc))
                    # code-matched: lots of the sell's code first (FIFO among them), then any open lot (FIFO)
                    sc = code.get(key); cneed = tot
                    for pas in (0, 1):
                        for l in list(cq):
                            if cneed <= 0.5: break
                            if pas == 0 and l["code"] != sc: continue
                            take = min(l["cleft"], cneed); MATCH[pas] += take
                            l["cout"] += gross * take / tot; l["cleft"] -= take; cneed -= take; l["csell_txc"] += stc * take / tot
                            if l["cleft"] <= 0.5: l["cclose_cc"] = float(cca[k]); cq.remove(l)
                    nl = 0
                    while need > 0.5 and q:
                        l = q[0]; take = min(l["left"], need)
                        l["out"] += gross * take / tot; l["left"] -= take; need -= take; l["nsell"] += 1; nl += 1
                        l["sell_txc"] += stc * take / tot
                        if l["left"] <= 0.5: l["close_cc"] = float(cca[k]); l["close_slot"] = int(sl[k]); q.pop(0)
                    if need > 0.5 * tot and need > 0.01 * trip["peak"]: trip["gap"] = True      # sold tokens we never saw bought (coverage gap)
                if trip is None: continue
                bal -= tk[k]
                if bal < -0.01 * trip["peak"]: trip["gap"] = True
                if bal <= 0.005 * trip["peak"]:
                    trip["close_slot"] = int(sl[k]); trip["close_bt"] = int(bt[k]); trip["close_cc"] = float(cca[k]); bal = 0.0
                    for l in q: l["close_cc"] = float(cca[k]); l["dust"] = True
                    for l in cq: l["cclose_cc"] = float(cca[k])
                    q = []; cq = []
                    for li in trip["lots"]:
                        if LOTS[li]["pleft"] > 0: LOTS[li]["pleft"] = 0.0; LOTS[li]["pclose_cc"] = float(cca[k])
        # open at end: mark at last price x (1 - 1.25%)
        for l in q:
            l["mark"] = l["left"] * px[-1] * 0.9875
        for l in cq:
            l["cmark"] = l["cleft"] * px[-1] * 0.9875
        if trip is not None and trip["close_cc"] is None:
            trip["open_end"] = True; trip["mark"] = bal * px[-1] * 0.9875
        nm_done += 1
        if nm_done % 5000 == 0: print(f"  {nm_done:,} mints, {len(BUYS):,} buys ({time.time() - t0:.0f}s)", flush=True)
    for t in TRIPS:
        t["ntx"] = len(t["txs"]); t["txc"] = sum(cost.get(x, TXC_DEF) + FAILSH for x in t["txs"]); t["meas_cost"] = all(x in cost for x in t["txs"])
        del t["txs"]
        h0 = (t["bt0"] + 18000) // 3600 * 3600 - 18000
        hc = ((t["close_bt"] or t["bt0"]) + 18000) // 3600 * 3600 - 18000
        t["usable"] = h0 in good and hc in good
    pickle.dump(dict(buys=BUYS, lots=LOTS, sells=SELLS, trips=TRIPS), open(f"{OUT}/p1.pkl", "wb"))
    print(f"code-matched sell tokens: same code {MATCH[0] / max(sum(MATCH), 1):.4f}, other code {MATCH[1] / max(sum(MATCH), 1):.4f}")
    print(f"buys {len(BUYS):,} lots {len(LOTS):,} sells {len(SELLS):,} trips {len(TRIPS):,} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
