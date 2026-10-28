#!/usr/bin/env python3
"""GAP step 1 (read-only, offline): every buy (= lot) of haqq and of our two live wallets on the WHOLE merged tape
(dv8/tab, 10-22 03:07 -> 10-28 01:12 PKT), FIFO lot P&L, and the chain context of each buy (only rows before it: causal).

Lot P&L (MEASURED from the tape): sell proceeds net of pump fees (FIFO share) - gross buy cost (incl. pump fees)
  - tx costs: buy tx fee+tips + token-share of each sell tx's fee+tips.
  haqq tx costs from haqq_strat/haqq_raw.jsonl where the (slot, idx) is there (10-25 19:20 -> 10-28 00:41 PKT, MEASURED);
  elsewhere the per-tx mean of the covered period (INFERRED, flagged cost_ok=False). Our tx costs from dv8/tab/ours.jsonl.
  Lots still open at the tape end are marked at the last price x (1 - 1.25%) (flag open=True).
Dump context = the biggest single-trade price drop by an outside SELL in the last 5 slots before the buy (same as haqq_strat s1),
  plus: seller id, seller's balance (% of supply) before the dump, our engine's dump envelope checks on that sell
  (IMIT1.json envelope: sell >= 1.08 SOL, drop >= 4.65 %, age <= 343.67 s; dump_events: age >= 1 s, curve < 100 SOL,
  first >= 1 SOL sell of its slot; since_buy <= 3.869 s), launch filter (mayhem / curve < 25 SOL / early curve > 200 SOL).
Type (haqq_strat hs_lib.etype): ADD / DEAD / DIP / LAUNCH / DIP_LATE / MOMO / OTHER; probe = size <= 0.05 SOL.
Out: /home/moiz/sniper-data/haqq_dissect/gap/g1_lots.pkl"""
import json, time, collections, pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
SUP = 1e15; DEAD_V = 30.52


def etype(b):
    if b["add"]: return "ADD"
    if b["vsol_pre"] <= DEAD_V: return "DEAD"
    if b.get("d_drop", 0) >= 0.05 and b.get("d_slots", 99) <= 2: return "DIP"
    if b["age"] is not None and b["age"] <= 5: return "LAUNCH"
    if b.get("dd10", 0) >= 0.10: return "DIP_LATE"
    if b.get("wb_sol", 0) >= 1.0 and (b.get("wb_slots") if b.get("wb_slots") is not None else 99) <= 2: return "MOMO"
    return "OTHER"


def main():
    t0 = time.time()
    ids, idm = L.ids_map()
    WHO = {idm[L.HAQQ]: "haqq"}
    for nm, w in L.WAL.items():
        if w in idm: WHO[idm[w]] = nm
    # ---- tx costs per (slot, idx)
    cost = {}; hq_n = 0; hq_sum = 0.0; hq_fail = collections.Counter(); hq_failfee = collections.Counter(); hq_land = collections.Counter()
    for l in open("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl"):
        d = json.loads(l)
        if not d["signers"] or d["signers"][0] != L.HAQQ: continue
        tip = sum(v for a, v in (d.get("tips") or []))
        day = L.day_of(d["bt"])
        if d["err"] is not None:
            hq_fail[day] += 1; hq_failfee[day] += d["fee"] / 1e9; continue
        hq_land[day] += 1
        cost[(d["s"], d["i"])] = (d["fee"] + tip) / 1e9; hq_n += 1; hq_sum += (d["fee"] + tip) / 1e9
    hq_mean = hq_sum / hq_n
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l)
        if d["signers"][0] not in L.WAL.values(): continue
        tip = sum(v for a, v in (d.get("tips") or []))
        cost[(d["s"], d["i"])] = (d["fee"] + tip) / 1e9
    print(f"costs: haqq landed txs with cost {hq_n:,} mean {1e3 * hq_mean:.3f} mSOL; failed per day {dict(hq_fail)} ({time.time() - t0:.0f}s)", flush=True)
    # ---- tape subset: mints touched by the wallets
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    us_all = np.asarray(T["user"]); sg_all = np.asarray(T["signer"])
    wid = np.array(list(WHO), np.uint32)
    mine = np.isin(us_all, wid) | np.isin(sg_all, wid)
    mints = np.unique(np.asarray(T["mint"])[mine])
    sel = np.flatnonzero(np.isin(np.asarray(T["mint"]), mints))
    del us_all, sg_all, mine
    S = np.asarray(T[sel])
    o = np.lexsort((S["j"], S["idx"], S["slot"], S["mint"])); S = S[o]
    um, st_, = np.unique(S["mint"], return_index=True); en_ = np.append(st_[1:], len(S))
    print(f"mints {len(mints):,}, rows {len(S):,} ({time.time() - t0:.0f}s)", flush=True)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    buys, lots = [], []
    for n_m, (mi, a, e) in enumerate(zip(um.tolist(), st_.tolist(), en_.tolist())):
        mint = ids[mi]; c = CR.get(mint)
        cs = int(c["slot"]) if c and c.get("slot") is not None else None
        cr_id = idm.get(c.get("creator"), -2) if c else -2
        mayhem = bool(c.get("mayhem")) if c else None
        X = S[a:e]
        sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
        us = X["user"].astype(np.int64); sg = X["signer"].astype(np.int64); bu = X["buy"].astype(bool)
        so = X["sol"].astype(np.float64) / 1e9; tk = X["tok"].astype(np.float64)
        vs = X["vsol"].astype(np.float64) / 1e9; vt = X["vtok"].astype(np.float64); bt = X["bt"].astype(np.int64)
        fee = (X["fee_bps"].astype(np.float64) + X["cfee_bps"]) / 1e4
        n = len(sl)
        px = vs / np.maximum(vt, 1)
        v_c = float(c["vsol"]) / 1e9 if c and c.get("vsol") else 30.0; t_c = float(c["vtok"]) if c and c.get("vtok") else 1.073e15
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        vsp = np.empty(n); vsp[0] = v_c; vsp[1:] = vs[:-1]
        drop = np.where(~bu, 1 - px / pxp, 0.0)
        acct = np.full(n, -1, np.int64)
        for u in WHO: acct[(us == u) | (sg == u)] = u
        cca = L.cc(sl, ix)
        bundl = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
        early = set(us[(sl <= (cs + 10 if cs is not None else -1)) & bu].tolist())
        lf_ok = (not mayhem) and float(vs.min()) >= 25.0 and float(vs[:50].max()) <= 200.0
        stok = np.where(bu, tk, -tk)
        for u in set(acct[acct >= 0].tolist()):
            W = WHO[u]; q = collections.deque(); bal = 0.0; peak = 0.0; trip = -1; ntrip = 0
            for k in np.flatnonzero(acct == u).tolist():
                ck = cost.get((int(sl[k]), int(ix[k])))
                if bu[k]:
                    gc = so[k] * (1 + fee[k])
                    add = bal > 0.005 * peak and bal > 0
                    if not add: ntrip += 1; peak = 0.0
                    LT = dict(cost=gc, tok=tk[k], left=tk[k], out=0.0, sx=0.0, sx_ok=True, close_slot=None, close_bt=None, close_cc=None,
                              nsell=0, txc=ck, mark=0.0)
                    lots.append(LT); q.append(LT)
                    bal += tk[k]; peak = max(peak, bal)
                    lo5 = int(np.searchsorted(sl, sl[k] - 5)); lo3 = int(np.searchsorted(sl, sl[k] - 3)); lo10 = int(np.searchsorted(sl, sl[k] - 10))
                    cand = [j for j in range(lo5, k) if not bu[j] and acct[j] != u]
                    dj = max(cand, key=lambda j: drop[j]) if cand else None
                    D = {}
                    if dj is not None and drop[dj] > 0:
                        seller = int(us[dj])
                        st = ("dev" if seller == cr_id else "bundler" if seller in bundl else "early" if seller in early else "other")
                        if acct[dj] >= 0: st = "wallet:" + WHO[int(acct[dj])]
                        bw = slice(dj + 1, k); bb = bu[bw] & (acct[bw] != u)
                        nxt = int(bb.sum())
                        sbal = float(stok[:dj][us[:dj] == seller].sum())            # seller's tokens before the dump
                        lb = np.flatnonzero(bu[:dj]); since_buy = float((cca[dj] - cca[lb[-1]]) / 1000.0) if len(lb) else 1e9
                        same = np.flatnonzero((sl[:dj] == sl[dj]) & ~bu[:dj] & (so[:dj] >= 1.0))
                        age_s = (sl[dj] - cs) * 0.212 if cs is not None else None
                        D = dict(d_drop=float(drop[dj]), d_sol=float(so[dj]), d_pct=float(tk[dj] / SUP * 100), d_type=st, d_user=seller,
                                 d_bal_pct=100 * sbal / SUP, d_slots=int(sl[k] - sl[dj]), d_ms=float(cca[k] - cca[dj]), d_nbuy=nxt,
                                 d_nw=len(set(us[bw][bb].tolist())), d_bsol=float(so[bw][bb].sum()), d_first=nxt == 0,
                                 d_slot=int(sl[dj]), d_i=int(ix[dj]), d_bt=int(bt[dj]), d_vpost=float(vs[dj]), d_age_s=age_s,
                                 d_since_buy=since_buy, d_first_big=len(same) == 0)
                    wb = [j for j in range(lo3, k) if bu[j] and acct[j] != u]
                    bj = max(wb, key=lambda j: so[j]) if wb else None
                    mx10 = float(px[lo10:k].max()) if k > lo10 else pxp[k]
                    B = dict(w=W, mint=mint, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cc=float(cca[k]), size=gc, cs=cs,
                             age=int(sl[k] - cs) if cs is not None else None, vsol_pre=float(vsp[k]), dd10=float(1 - pxp[k] / mx10) if mx10 > 0 else 0.0,
                             wb_sol=float(so[bj]) if bj is not None else 0.0, wb_slots=int(sl[k] - sl[bj]) if bj is not None else None,
                             add=bool(add), ntrip=ntrip, lot=len(lots) - 1, mayhem=mayhem, lf_ok=lf_ok, **D)
                    B["type"] = etype(B)
                    buys.append(B)
                else:
                    gross = so[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                    while need > 0.5 and q:
                        LT = q[0]; take = min(LT["left"], need)
                        LT["out"] += gross * take / tot; LT["left"] -= take; need -= take; LT["nsell"] += 1
                        if ck is not None: LT["sx"] += ck * take / tot
                        else: LT["sx_ok"] = False; LT["sx"] += (hq_mean if W == "haqq" else 0.0) * take / tot
                        if LT["left"] <= 0.5:
                            LT["close_slot"] = int(sl[k]); LT["close_bt"] = int(bt[k]); LT["close_cc"] = float(cca[k]); q.popleft()
                    bal -= tk[k]
                    if bal <= 0.005 * peak: bal = 0.0
            for LT in q:
                LT["mark"] = LT["left"] * px[-1] * (1 - 0.0125)
        if n_m % 5000 == 0: print(f"  {n_m:,}/{len(um):,} mints, buys {len(buys):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- lot P&L
    for B in buys:
        LT = lots[B["lot"]]
        txb = LT["txc"] if LT["txc"] is not None else (hq_mean if B["w"] == "haqq" else 0.0)
        B["cost_ok"] = LT["txc"] is not None and LT["sx_ok"]
        B["gross"] = LT["out"] + LT["mark"] - LT["cost"]
        B["txc"] = txb + LT["sx"]
        B["net"] = B["gross"] - B["txc"]
        B["open"] = LT["close_slot"] is None
        B["hold_s"] = (LT["close_cc"] - B["cc"]) / 1000.0 if LT["close_cc"] else None
        B["close_slot"] = LT["close_slot"]; B["nsell"] = LT["nsell"]
        B["day"] = L.day_of(B["bt"]); B["probe"] = B["size"] <= 0.05
    meta = dict(hq_mean_txc=hq_mean, hq_fail=dict(hq_fail), hq_failfee=dict(hq_failfee), hq_land=dict(hq_land))
    pickle.dump(dict(buys=buys, meta=meta), open(f"{OUT}/g1_lots.pkl", "wb"))
    c = collections.Counter((b["w"], b["day"]) for b in buys)
    print(sorted(c.items())); print(f"done {len(buys):,} buys ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
