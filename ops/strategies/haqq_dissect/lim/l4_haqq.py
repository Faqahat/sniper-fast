#!/usr/bin/env python3
"""LIM step 4 (read-only): every haqq BUY tx 10-22 03:08 -> 10-28 00:41 PKT (filled AND failed; data/lim/hbuys.pkl) placed on the
dv8 tape (all pump.fun trades, chain order). Per buy, MEASURED:
  * the curve state just before his tx position (all rows with key < his (slot, idx));
  * the trigger dump = the outside sell with the biggest single-trade price drop in the last 5 slots (as haqq_strat s1);
  * pr  = price before his tx / post-dump price; pr0 = price before his tx / pre-dump price;
  * tokens his spend would get at the post-dump state, at the pre-dump state and at his position (tok_d, tok_0, tok_p);
  * outside trades / buys / wallets between the dump and him; slots and chain-clock ms after the dump;
  * for fills: FIFO lot P&L (sells consume lots FIFO by tokens; proceeds net of pump fees; open lots marked at the last
    price x 0.9875) over the whole tape; hold in slots.
Spend of a failed buy = his modal spend is unknown -> taken from the RPC sample when present, else 0.40 (INFERRED; only
used for tok_* ratios, which barely depend on size).
Out: data/lim/hctx.pkl"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"


def main():
    t0 = time.time()
    HB = pickle.load(open(f"{OUT}/hbuys.pkl", "rb"))
    ids, idm = L.ids_map(); hid = idm[L.HAQQ]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[b["mint"]] for b in HB if b["mint"] in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    print(f"tape rows {len(TT):,} mints {len(span):,} ({time.time() - t0:.0f}s)", flush=True)
    by = collections.defaultdict(list)
    for b in HB: by[b["mint"]].append(b)
    out = []; nm = 0
    for mint, bl in by.items():
        if mint not in span: continue
        a, b = span[mint]; R = TT[a:b]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        us = R["user"].astype(np.int64); sg = R["signer"].astype(np.int64)
        fee = (R["fee_bps"].astype(np.float64) + R["cfee_bps"]) / 1e4
        mine = (us == hid) | (sg == hid)
        px = vs / np.maximum(vt, 1)
        pxp = np.empty(len(R)); pxp[0] = px[0]; pxp[1:] = px[:-1]
        drop = np.where(~bu & ~mine, 1 - px / pxp, 0.0); drop[0] = 0
        # FIFO lots over his rows
        lots = {}; q = collections.deque()
        for k in np.flatnonzero(mine).tolist():
            if bu[k]:
                Lt = dict(cost=sol[k] * (1 + fee[k]), tok=tk[k], left=tk[k], out=0.0, close=None, last=None); lots[int(key[k])] = Lt; q.append(Lt)
            else:
                gross = sol[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                while need > 0.5 and q:
                    Lt = q[0]; take = min(Lt["left"], need)
                    Lt["out"] += gross * take / tot; Lt["left"] -= take; need -= take; Lt["last"] = int(sl[k])
                    if Lt["left"] <= 0.5: Lt["close"] = int(sl[k]); q.popleft()
        for Lt in q: Lt["mark"] = Lt["left"] * px[-1] * 0.9875
        for hb in bl:
            uk = hb["s"] * 100000 + hb["i"]
            p = int(np.searchsorted(key, uk))          # first row with key >= his key
            if p < 1: continue
            pre = p - 1
            lo5 = int(np.searchsorted(sl, hb["s"] - 5))
            cand = np.arange(lo5, p)
            cand = cand[drop[cand] > 0]
            rec = dict(sig=hb["sig"], s=hb["s"], i=hb["i"], bt=hb["bt"], day=L.day_of(hb["bt"]), ok=hb["err"] is None, err=hb["err"], mint=mint,
                       fee=hb["fee"], tips=hb["tips"], v_pre=float(vs[pre]), px_pre=float(px[pre]))
            if hb["err"] is None:
                fk = np.flatnonzero((key == uk) & mine & bu)
                if len(fk):
                    k = int(fk[0]); Lt = lots.get(int(key[k]))
                    rec.update(spend=float(sol[k] * (1 + fee[k])), tok=float(tk[k]))
                    if Lt: rec.update(lot_pnl=Lt["out"] + Lt.get("mark", 0.0) - Lt["cost"], lot_cost=Lt["cost"], close=Lt["close"], open_=Lt["close"] is None)
            if len(cand):
                dj = int(cand[np.argmax(drop[cand])])
                btw = np.arange(dj + 1, p); ob = btw[~mine[btw]]
                rec.update(dj_drop=float(drop[dj]), d_sol=float(sol[dj]), d_slot=int(sl[dj]), d_idx=int(ix[dj]), d_slots=int(hb["s"] - sl[dj]),
                           d_ms=float(L.cc(hb["s"], hb["i"]) - L.cc(int(sl[dj]), int(ix[dj]))), v_post=float(vs[dj]),
                           pr=float(px[pre] / px[dj]), pr0=float(px[pre] / pxp[dj]),
                           n_ahead=len(ob), nb_ahead=int(bu[ob].sum()), nw_ahead=len(set(us[ob][bu[ob]].tolist())), b_ahead=float(sol[ob][bu[ob]].sum()),
                           mine_between=int(mine[btw].sum()), d_row=int(dj), vd=float(vs[dj]), td=float(vt[dj]), v0=float(vs[dj - 1]) if dj else None,
                           t0=float(vt[dj - 1]) if dj else None, vp=float(vs[pre]), tp=float(vt[pre]))
            out.append(rec)
        nm += 1
        if nm % 2000 == 0: print(nm, len(out), f"{time.time() - t0:.0f}s", flush=True)
    pickle.dump(out, open(f"{OUT}/hctx.pkl", "wb"))
    print("buys placed", len(out), "of", len(HB), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
