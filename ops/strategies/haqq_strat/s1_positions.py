#!/usr/bin/env python3
"""HAQQ_STRAT step 1 (read-only, offline): every buy and sell of haqq AND of our two live wallets on the multi-day tape
(haqq_model/tab, 10-23 19:26 -> 10-27 23:20 PKT), with the chain context just before each buy, FIFO lots, and tx costs.

Per buy (MEASURED from the tape):
  * create: age in slots and chain-clock ms after the create;
  * the biggest single-trade price drop by an outside SELL in the last 5 slots before the buy (the "dump"): drop %, SOL, seller
    type (dev / bundler / early / fbot / other), slots, index positions and chain-clock ms from the dump to the buy, distinct
    wallets and buy SOL that landed between the dump and the buy, and whether the buy is the first buy after the dump;
  * the biggest outside BUY in the last 3 slots (SOL, % supply) and the drop from the 10-slot high;
  * curve SOL before the buy (dead curve = <= 30.52), size, trip/lot bookkeeping.
Chain clock (same as presend/real/rlib.py): cc(s, i) = s*212 + i / n_s * 212, n_s = recorded block size.
Lots: each buy is a lot; sells consume lots FIFO by tokens. Lot P&L = share of sell proceeds (net of pump fees) - gross cost.
Costs: tx fee + tips of each landed tx, joined from the raw recording by (slot, idx) (haqq: haqq_raw.jsonl, 10-25 14:20 ->;
ours: tab/ours.jsonl). Failed txs are counted separately (s2).
Out: /home/moiz/sniper-data/haqq_strat/pos.pkl"""
import json, time, collections, pickle, sys
import numpy as np
TAB = "/home/moiz/sniper-data/haqq_model/tab"; OUT = "/home/moiz/sniper-data/haqq_strat"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "AMS"}
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
SMS = 212.0; SUP = 1e15


def main():
    t0 = time.time()
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    who = {idm[HAQQ]: "haqq"}
    for k, v in OURS.items():
        if k in idm: who[idm[k]] = v
    T = np.load(f"{TAB}/trades.npy")
    S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min())
    bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.int32); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1

    def cc(s, i):
        k = s - s0; n = bsz[k] if 0 <= k < len(bsz) else 0
        n = n if n > 0 else 400
        return s * SMS + i / max(float(n), i + 1.0) * SMS
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, st_ = np.unique(T["mint"], return_index=True); en_ = np.append(st_[1:], len(T))
    span = {int(m): (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    CR = json.load(open(f"{TAB}/creates.json"))
    fb_ids = {idm[w] for w in FB if w in idm}
    # raw costs
    cost = {}
    for f, wset in ((f"{OUT}/haqq_raw.jsonl", {HAQQ}), (f"{TAB}/ours.jsonl", set(OURS))):
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            if not d["signers"] or d["signers"][0] not in wset: continue
            tip = sum(v for a, v in (d.get("tips") or []))
            cost[(d["s"], d["i"])] = (d["fee"] + tip, d["fee"], tip, d.get("cu"), d.get("cul"), d.get("cup"),
                                      [a for a, v in (d.get("tips") or [])], d["err"] is not None)
    print(f"tape {len(T):,}; raw cost rows {len(cost):,} ({time.time() - t0:.0f}s)", flush=True)
    wid = np.array(list(who), np.uint32)
    mine = np.isin(T["user"], wid) | np.isin(T["signer"], wid)
    mints = np.unique(T["mint"][mine])
    buys, lots, sells, trips = [], [], [], []
    for mi in mints.tolist():
        a, e = span[mi]; mint = ids[mi]; c = CR.get(mint)
        cs = int(c["slot"]) if c and c.get("slot") is not None else None
        ci = int(c["idx"]) if c and c.get("idx") is not None else 0
        cr_id = idm.get(c.get("creator"), -2) if c else -2
        sl = T["slot"][a:e].astype(np.int64); ix = T["idx"][a:e].astype(np.int64)
        us = T["user"][a:e].astype(np.int64); sg = T["signer"][a:e].astype(np.int64); bu = T["buy"][a:e].astype(bool)
        so = T["sol"][a:e].astype(np.float64) / 1e9; tk = T["tok"][a:e].astype(np.float64)
        vs = T["vsol"][a:e].astype(np.float64) / 1e9; vt = T["vtok"][a:e].astype(np.float64); bt = T["bt"][a:e].astype(np.int64)
        fee = (T["fee_bps"][a:e].astype(np.float64) + T["cfee_bps"][a:e]) / 1e4
        n = len(sl)
        px = vs / np.maximum(vt, 1)
        v_c = float(c["vsol"]) / 1e9 if c and c.get("vsol") else 30.0; t_c = float(c["vtok"]) if c and c.get("vtok") else 1.073e15
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]                     # price before each trade
        vsp = np.empty(n); vsp[0] = v_c; vsp[1:] = vs[:-1]
        drop = np.where(~bu, 1 - px / pxp, 0.0)
        acct = np.full(n, -1, np.int64)
        for u, nm in who.items(): acct[(us == u) | (sg == u)] = u
        bundl = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
        early = set(us[(sl <= (cs + 10 if cs is not None else -1)) & bu].tolist())
        cc_c = cc(cs, ci) if cs is not None else None
        cca = np.array([cc(int(s), int(i)) for s, i in zip(sl, ix)])
        for u in set(acct[acct >= 0].tolist()):
            W = who[u]; hm = acct == u
            q = collections.deque(); bal = 0.0; trip = None
            for k in np.flatnonzero(hm).tolist():
                ck = cost.get((int(sl[k]), int(ix[k])))
                if bu[k]:
                    gc = so[k] * (1 + fee[k])
                    L = dict(w=W, mint=mint, k=k, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cost=gc, tok=tk[k], left=tk[k],
                             out=0.0, close_slot=None, close_bt=None, nsell=0, sells=[], txc=(ck[0] / 1e9 if ck else None))
                    lots.append(L); q.append(L)
                    if trip is None or bal <= 0:
                        trip = dict(w=W, mint=mint, slot0=int(sl[k]), bt0=int(bt[k]), cost=0.0, out=0.0, nb=0, ns=0, peak=0.0,
                                    close_slot=None, close_bt=None, lots=[], buys=[], txc=0.0, txc_ok=True)
                        trips.append(trip)
                    trip["cost"] += gc; trip["nb"] += 1; trip["lots"].append(len(lots) - 1); trip["buys"].append(len(buys))
                    if ck: trip["txc"] += ck[0] / 1e9
                    else: trip["txc_ok"] = False
                    bal += tk[k]; trip["peak"] = max(trip["peak"], bal)
                    # ---- context before the buy
                    lo5 = int(np.searchsorted(sl, sl[k] - 5)); lo3 = int(np.searchsorted(sl, sl[k] - 3))
                    lo10 = int(np.searchsorted(sl, sl[k] - 10)); lo2 = int(np.searchsorted(sl, sl[k] - 2))
                    oth = acct[:k] != u
                    cand = [j for j in range(lo5, k) if not bu[j] and acct[j] != u]
                    dj = max(cand, key=lambda j: drop[j]) if cand else None
                    D = {}
                    if dj is not None and drop[dj] > 0:
                        bw = slice(dj + 1, k); bb = bu[bw] & (acct[bw] != u)
                        seller = us[dj]
                        st = ("dev" if seller == cr_id else "bundler" if seller in bundl else "fbot" if seller in fb_ids
                              else "early" if seller in early else "other")
                        if acct[dj] >= 0: st = "us/haqq"
                        # first outside buy after the dump
                        nxt = [j for j in range(dj + 1, k) if bu[j] and acct[j] != u]
                        D = dict(d_drop=float(drop[dj]), d_sol=float(so[dj]), d_pct=float(tk[dj] / SUP * 100), d_type=st,
                                 d_slots=int(sl[k] - sl[dj]), d_idx=int(ix[k] - ix[dj]) if sl[k] == sl[dj] else None,
                                 d_ms=float(cca[k] - cca[dj]), d_nbuy=int(bb.sum()), d_nw=len(set(us[bw][bb].tolist())),
                                 d_bsol=float(so[bw][bb].sum()), d_first=len(nxt) == 0, d_row=a + dj, d_slot=int(sl[dj]), d_i=int(ix[dj]),
                                 d_vpost=float(vs[dj]), px_ratio=float(pxp[k] / px[dj]), d_age=int(sl[dj] - cs) if cs is not None else None)
                    wb = [j for j in range(lo3, k) if bu[j] and acct[j] != u]
                    bj = max(wb, key=lambda j: so[j]) if wb else None
                    mx10 = float(px[lo10:k].max()) if k > lo10 else pxp[k]
                    prev_hold = trip["nb"] > 1
                    B = dict(w=W, mint=mint, row=a + k, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cc=float(cca[k]), size=gc,
                             cs=cs, age=int(sl[k] - cs) if cs is not None else None, age_ms=float(cca[k] - cc_c) if cc_c else None,
                             vsol_pre=float(vsp[k]), pre_px=float(pxp[k]), dd10=float(1 - pxp[k] / mx10) if mx10 > 0 else 0.0,
                             wb_sol=float(so[bj]) if bj is not None else 0.0, wb_pct=float(tk[bj] / SUP * 100) if bj is not None else 0.0,
                             wb_slots=int(sl[k] - sl[bj]) if bj is not None else None, wb_ms=float(cca[k] - cca[bj]) if bj is not None else None,
                             wb_nw=len(set(us[bj + 1:k][bu[bj + 1:k] & (acct[bj + 1:k] != u)].tolist())) if bj is not None else None,
                             n_prev=k, add=prev_hold, trip_ix=len(trips) - 1, lot_ix=len(lots) - 1,
                             nd_buy_sol=float(so[:k][bu[:k] & oth & (us[:k] != cr_id)].sum()), dev_sold=bool((~bu[:k] & (us[:k] == cr_id)).any()),
                             cost=ck, **D)
                    # what happened right after (first 10 slots) - for diagnostics only
                    hi = int(np.searchsorted(sl, sl[k] + 10, side="right"))
                    af = slice(k + 1, hi); ab = bu[af] & (acct[af] != u)
                    B["fol_bsol10"] = float(so[af][ab].sum()); B["fol_ssol10"] = float(so[af][~bu[af] & (acct[af] != u)].sum())
                    buys.append(B)
                else:
                    gross = so[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                    # sell context
                    j = k - 1
                    while j >= 0 and acct[j] == u: j -= 1
                    lo2 = int(np.searchsorted(sl, sl[k] - 2))
                    ob = [jj for jj in range(lo2, k) if acct[jj] != u]
                    Sx = dict(w=W, mint=mint, row=a + k, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cc=float(cca[k]), sol=gross, tok=tk[k],
                              last_buy=bool(bu[j]) if j >= 0 else None, last_sol=float(so[j]) if j >= 0 else None,
                              last_ms=float(cca[k] - cca[j]) if j >= 0 else None,
                              big_buy2=float(max([so[jj] for jj in ob if bu[jj]], default=0.0)),
                              big_sell2=float(max([so[jj] for jj in ob if not bu[jj]], default=0.0)),
                              px_pre=float(pxp[k]), cost=ck, lots=[])
                    if trip is not None:
                        trip["out"] += gross; trip["ns"] += 1
                        if ck: trip["txc"] += ck[0] / 1e9
                        else: trip["txc_ok"] = False
                    while need > 0.5 and q:
                        L = q[0]; take = min(L["left"], need)
                        L["out"] += gross * take / tot; L["left"] -= take; need -= take; L["nsell"] += 1
                        L["sells"].append((int(sl[k]), take / L["tok"], float(pxp[k])))
                        Sx["lots"].append(lots.index(L) if False else id(L))
                        if L["left"] <= 0.5: L["close_bt"] = int(bt[k]); L["close_slot"] = int(sl[k]); L["close_cc"] = float(cca[k]); q.popleft()
                    sells.append(Sx)
                    bal -= tk[k]
                    if trip is not None and bal <= 0.005 * trip["peak"]:
                        trip["close_bt"] = int(bt[k]); trip["close_slot"] = int(sl[k]); bal = 0.0
            for L in q:
                L["mark"] = L["left"] * px[-1] * 0.9875; L["last_slot"] = int(sl[-1])
    print(f"buys {len(buys):,} lots {len(lots):,} sells {len(sells):,} trips {len(trips):,} ({time.time() - t0:.0f}s)", flush=True)
    for L in lots: L.pop("sells_ids", None)
    for Sx in sells: Sx.pop("lots", None)
    pickle.dump(dict(buys=buys, lots=lots, sells=sells, trips=trips), open(f"{OUT}/pos.pkl", "wb"))


if __name__ == "__main__":
    main()
