#!/usr/bin/env python3
"""HAQQ_SIZE step 1 (read-only, offline): every haqq buy on the multi-day tape (haqq_model/tab, 10-23 19:26 -> 10-27 23:20 PKT)
with features knowable at his buy, plus FIFO lot accounting of his realized P&L.
  size   = gross SOL budget = curve SOL x (1 + (fee_bps + cfee_bps) / 1e4)   (MEASURED, from the trade event)
  lots   = each buy is a lot; his sells consume lots FIFO by tokens; a lot's P&L = its share of sell proceeds (net of pump fees)
           minus its gross cost. Tx fees / tips are NOT on the tape (P&L is gross of them).
  trip   = a run of his trades on one mint from a zero token balance back to (near) zero.
Out: /home/moiz/sniper-data/haqq_size/buys.pkl (list of dicts) and lots/trips."""
import json, time, collections, pickle, bisect
import numpy as np
TAB = "/home/moiz/sniper-data/haqq_model/tab"; OUT = "/home/moiz/sniper-data/haqq_size"; HM = "/home/moiz/sniper-data/haqq_model"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))


def main():
    t0 = time.time()
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}; h = idm[HAQQ]
    T = np.load(f"{TAB}/trades.npy")
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, st_ = np.unique(T["mint"], return_index=True); en_ = np.append(st_[1:], len(T))
    span = {int(m): (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    CR = json.load(open(f"{TAB}/creates.json"))
    fb_ids = {idm[w] for w in FB if w in idm}; coh_ids = {idm[w] for w in COH if w in idm}
    sc = {}
    for n in (0, 14):
        Z = __import__("pickle").load(open(f"{HM}/model_n{n}.pkl", "rb"))
        sc[n] = {m: (float(s), int(sl)) for m, s, sl in zip(Z["mint"], Z["score"], Z["slot"])}
    print(f"tape loaded {time.time() - t0:.0f}s", flush=True)
    ishq = T["user"] == h
    hq_mints = np.unique(T["mint"][ishq])
    buys = []; lots = []; trips = []
    for mi in hq_mints.tolist():
        a, e = span[mi]
        mint = ids[mi]; c = CR.get(mint)
        cs = int(c["slot"]) if c and c.get("slot") is not None else None
        cr_id = idm.get(c.get("creator"), -2) if c else -2
        sl = T["slot"][a:e].astype(np.int64); us = T["user"][a:e]; bu = T["buy"][a:e].astype(bool)
        so = T["sol"][a:e].astype(np.float64) / 1e9; tk = T["tok"][a:e].astype(np.float64)
        vs = T["vsol"][a:e].astype(np.float64) / 1e9; vt = T["vtok"][a:e].astype(np.float64); bt = T["bt"][a:e].astype(np.int64)
        fee = (T["fee_bps"][a:e].astype(np.float64) + T["cfee_bps"][a:e]) / 1e4
        hm = us == h
        px = vs / np.maximum(vt, 1)
        nd = ~hm & (us != cr_id)
        # FIFO lots
        q = collections.deque(); bal = 0.0; trip = None
        for k in np.flatnonzero(hm).tolist():
            if bu[k]:
                cost = so[k] * (1 + fee[k])
                L = dict(mint=mint, k=a + k, slot=int(sl[k]), bt=int(bt[k]), cost=cost, tok=tk[k], left=tk[k], out=0.0, close_bt=None)
                lots.append(L); q.append(L)
                if trip is None or bal <= 0:
                    trip = dict(mint=mint, bt0=int(bt[k]), slot0=int(sl[k]), cost=0.0, out=0.0, nb=0, ns=0, peak=0.0, close_bt=None, lots=[])
                    trips.append(trip)
                trip["cost"] += cost; trip["nb"] += 1; trip["lots"].append(len(lots) - 1)
                bal += tk[k]; trip["peak"] = max(trip["peak"], bal)
                # features
                kk = k                                  # state before his buy = trade k-1 on this mint
                pre_v = vs[k - 1] if k > 0 else (float(c["vsol"]) / 1e9 if c else 30.0)
                pre_t = vt[k - 1] if k > 0 else (float(c["vtok"]) if c else 1.073e15)
                pre_px = pre_v / max(pre_t, 1)
                prev = slice(0, k)
                lo10 = int(np.searchsorted(sl, sl[k] - 10)); lo3 = int(np.searchsorted(sl, sl[k] - 2))
                win10 = px[lo10:k]; mx10 = float(win10.max()) if k > lo10 else pre_px
                sells3 = (~bu[lo3:k]) & ~hm[lo3:k]
                big_sell = float(so[lo3:k][sells3].max()) if sells3.any() else 0.0
                # biggest single-trade price drop by a non-haqq sell in the last 3 slots
                dd = 0.0
                for j in range(max(lo3, 1), k):
                    if not bu[j] and not hm[j]: dd = max(dd, 1 - px[j] / px[j - 1])
                early = (sl[:k] <= (cs + 14 if cs is not None else -1))
                ew = set(us[:k][~hm[:k]].tolist())
                prev_mine = int((hm[:k] & bu[:k]).sum())
                B = dict(mint=mint, row=a + k, slot=int(sl[k]), bt=int(bt[k]), size=cost, size_net=so[k], cs=cs,
                         age=int(sl[k] - cs) if cs is not None else -1, vsol_pre=pre_v, mcap_px=pre_px,
                         nd_early=float(so[:k][bu[:k] & nd[:k] & early].sum()),
                         nd_before=float(so[:k][bu[:k] & nd[:k]].sum()),
                         sell_before=float(so[:k][~bu[:k] & ~hm[:k]].sum()),
                         dev_buy=float(so[:k][bu[:k] & (us[:k] == cr_id)].sum()), dev_sold=float((~bu[:k] & (us[:k] == cr_id)).any()),
                         bundle_n=float(len(set(us[:k][nd[:k] & bu[:k] & (sl[:k] == cs)].tolist()))) if cs is not None else 0.0,
                         bundle_sol=float(so[:k][nd[:k] & bu[:k] & (sl[:k] == cs)].sum()) if cs is not None else 0.0,
                         n_trades=k, n_traders=len(ew), big_sell3=big_sell, drop_sell3=dd, drop10=1 - pre_px / mx10 if mx10 > 0 else 0.0,
                         fb_n=len(ew & fb_ids), coh_n=len(ew & coh_ids), hour=time.gmtime(int(bt[k]) + 18000).tm_hour,
                         prev_mine=prev_mine, add=bool(bal - tk[k] > 0.005 * trip["peak"]) or trip["nb"] > 1,
                         trip_ix=len(trips) - 1, lot_ix=len(lots) - 1,
                         s0=sc[0].get(mint, (np.nan, 0))[0], s14=sc[14].get(mint, (np.nan, 0))[0],
                         s14_ok=bool(mint in sc[14] and sl[k] >= sc[14][mint][1] + 14))
                buys.append(B)
            else:
                proceeds = so[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                if trip is not None: trip["out"] += proceeds; trip["ns"] += 1
                while need > 0.5 and q:
                    L = q[0]; take = min(L["left"], need)
                    L["out"] += proceeds * take / tot; L["left"] -= take; need -= take
                    if L["left"] <= 0.5: L["close_bt"] = int(bt[k]); L["close_slot"] = int(sl[k]); q.popleft()
                bal -= tk[k]
                if trip is not None and bal <= 0.005 * trip["peak"]:
                    trip["close_bt"] = int(bt[k]); trip["close_slot"] = int(sl[k]); bal = 0.0
        last_px = px[-1]
        for L in q: L["mark"] = L["left"] * last_px * 0.99 / 1.0; L["last_vsol"] = float(vs[-1])
    print(f"buys {len(buys):,} lots {len(lots):,} trips {len(trips):,} ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(buys=buys, lots=lots, trips=trips), open(f"{OUT}/buys.pkl", "wb"))


if __name__ == "__main__":
    main()
