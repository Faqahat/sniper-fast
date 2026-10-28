#!/usr/bin/env python3
"""vs248 step 1 (read-only, offline): bot 248's lots and OUR filled lots on the merged tape (dv8/tab, 10-22 03:07 -> 10-28 01:12 PKT),
with the SAME dump definition for both, signatures, tx costs and the rows needed for exact-curve replays.

248 lot  = a haqq buy row whose tx carries CU-price code 248 (pos/codes.pkl); sells FIFO within (mint, code) (code-matched, 99.97%).
our lot  = a buy row signed by FRA 2g7r / AMS Egxf; sells FIFO within (wallet, mint). Path by the buy tx's CU limit (120k pre-send,
           100k regular) from tab/ours.jsonl.
P&L (MEASURED tape): sell SOL x (1 - fee) token share - buy SOL x (1 + fee) - tx costs (buy fee+tips + token share of sell fee+tips).
  haqq tx cost from codes.pkl where recorded, else 0.396 mSOL/tx (flag). Open at tape end: last price x (1 - 1.25 %).
Dump (both sides identical) = the biggest single-row price drop by a SELL that is neither haqq nor ours in slots [buy-5, buy], before the
  buy row. dump-reactive: drop >= 5 % and buy slot - dump slot <= 2.
Seller class: dev (creator) / bundler (bought in the create slot) / whale (held >= 6 % of supply before the dump) / early (bought
  <= create+10 slots) / other. chunk = the sell is < 5 % of supply and the pre-buy price is 4-30 % below the 10-slot high.
Out: vs248/v1.pkl (lots, our failed attempts, sig maps) and scratch tape subset (mints touched by 248 or us)."""
import json, pickle, sys, time, collections, glob, os
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_vs248"
SUP = 1e15; TXC_DEF = 0.000396
BOT = 248


def main():
    t0 = time.time()
    ids, idm = L.ids_map()
    H = idm[L.HAQQ]; OURW = {idm[w]: n for n, w in L.WAL.items()}
    CODES = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/pos/codes.pkl", "rb"))
    hcode = {k: v[0] for k, v in CODES.items() if k[0] != "F"}
    hcost = {k: v[1] for k, v in CODES.items() if k[0] != "F"}
    # haqq sigs (landed + failed) from the exec extraction + haqq_raw
    hsig = {}; hfail = []
    files = [f for f in glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl") if os.path.exists(f + ".done")]
    files.append("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl")
    for f in files:
        for l in open(f):
            if "haqqiUUXB5gp7" not in l: continue
            try: d = json.loads(l)
            except Exception: continue
            if not d.get("signers") or d["signers"][0] != L.HAQQ: continue
            if d["err"] is None: hsig[(d["s"], d["i"])] = d["sig"]
            else:
                ix = d.get("ixn") or []
                if any(x.startswith("Buy") for x in ix):
                    hfail.append(dict(s=d["s"], i=d["i"], sig=d["sig"], code=(d.get("cup") or 0) % 1000, mint=(d.get("mints") or [None])[0],
                                      err=str(d["err"]), fee=d["fee"] / 1e9, bt=d["bt"]))
    print(f"haqq sigs {len(hsig):,}, failed buys {len(hfail):,} ({time.time() - t0:.0f}s)", flush=True)
    # our txs
    osig = {}; ocost = {}; ocul = {}; ofail = []
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l)
        w = d["signers"][0]
        if w not in L.WAL.values(): continue
        tip = sum(v for a, v in (d.get("tips") or []))
        ix = d.get("ixn") or []
        if d["err"] is None:
            osig[(d["s"], d["i"])] = d["sig"]; ocost[(d["s"], d["i"])] = (d["fee"] + tip) / 1e9; ocul[(d["s"], d["i"])] = d.get("cul")
        elif any(x.startswith("Buy") for x in ix):
            es = str(d["err"])
            ofail.append(dict(s=d["s"], i=d["i"], sig=d["sig"], w=[n for n, ww in L.WAL.items() if ww == w][0], mint=(d.get("mints") or [None])[0],
                              cul=d.get("cul"), code="6042" if "6042" in es else es[:40], cost=(d["fee"] + tip) / 1e9, bt=d["bt"]))
    print(f"our landed {len(osig):,}, failed buys {len(ofail):,} ({time.time() - t0:.0f}s)", flush=True)
    # tape subset
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    sg = np.asarray(T["signer"]); us = np.asarray(T["user"]); bu = np.asarray(T["buy"]); mi = np.asarray(T["mint"])
    sl_all = np.asarray(T["slot"]); ix_all = np.asarray(T["idx"])
    hb = np.flatnonzero((sg == H) & (bu == 1))
    is248 = np.array([hcode.get((int(s), int(i))) == BOT for s, i in zip(sl_all[hb], ix_all[hb])])
    m248 = np.unique(mi[hb[is248]])
    ob = np.isin(sg, list(OURW)) & (bu == 1)
    mours = np.unique(mi[ob])
    mints = np.union1d(m248, mours)
    sel = np.flatnonzero(np.isin(mi, mints))
    del sg, us, bu, sl_all, ix_all
    S = np.asarray(T[sel]); S = S[np.lexsort((S["j"], S["idx"], S["slot"], S["mint"]))]
    del mi
    print(f"248 buy rows {is248.sum():,} on {len(m248):,} mints; our buy rows {ob.sum():,} on {len(mours):,} mints; subset rows {len(S):,} ({time.time() - t0:.0f}s)", flush=True)
    np.save(f"{SCR}/tape_sub.npy", S)
    ccall = L.cc(S["slot"].astype(np.int64), S["idx"].astype(np.int64)); np.save(f"{SCR}/tape_cc.npy", ccall)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    um, st_ = np.unique(S["mint"], return_index=True); en_ = np.append(st_[1:], len(S))
    LOTS = []
    for n_m, (m, a, e) in enumerate(zip(um.tolist(), st_.tolist(), en_.tolist())):
        mint = ids[m]; c = CR.get(mint) or {}
        cs = int(c["slot"]) if c.get("slot") is not None else None
        cr = idm.get(c.get("creator"), -2); mayhem = bool(c.get("mayhem"))
        X = S[a:e]; n = e - a
        sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
        u = X["user"].astype(np.int64); g = X["signer"].astype(np.int64); b = X["buy"].astype(bool)
        so = X["sol"].astype(np.float64) / 1e9; tk = X["tok"].astype(np.float64)
        vs = X["vsol"].astype(np.float64) / 1e9; vt = X["vtok"].astype(np.float64); bt = X["bt"].astype(np.int64)
        fee = (X["fee_bps"].astype(np.float64) + X["cfee_bps"]) / 1e4
        cc = ccall[a:e]
        px = vs / np.maximum(vt, 1)
        v_c = float(c.get("vsol") or 30e9) / 1e9; t_c = float(c.get("vtok") or 1.073e15)
        pxp = np.empty(n); pxp[0] = v_c / t_c; pxp[1:] = px[:-1]
        with np.errstate(divide="ignore", invalid="ignore"): drop = np.where(~b, 1 - px / pxp, 0.0)
        who = np.full(n, "", object)
        hq = (g == H) | (u == H)
        own = np.zeros(n, bool)
        for wid, nm in OURW.items():
            msk = (g == wid) | (u == wid); who[msk] = nm; own |= msk
        who[hq] = "haqq"
        outside = ~hq & ~own
        code = np.array([hcode.get((int(s_), int(i_)), -1) if hq[k] else -1 for k, (s_, i_) in enumerate(zip(sl, ix))])
        bundl = set(u[(sl == cs) & b].tolist()) if cs is not None else set()
        early = set(u[(sl <= (cs + 10 if cs is not None else -1)) & b].tolist())
        stok = np.where(b, tk, -tk)
        # owner key for lots: ('248',) or ('FRA'/'AMS',)
        def owner(k):
            if hq[k]: return ("haqq", int(code[k]))
            if own[k]: return (who[k], 0)
            return None
        Q = collections.defaultdict(collections.deque)
        for k in range(n):
            ow = owner(k)
            if ow is None: continue
            if ow[0] == "haqq" and ow[1] != BOT: continue
            key = (ow[0], ow[1])
            if b[k]:
                if ow[0] == "haqq": txc = hcost.get((int(sl[k]), int(ix[k]))); sig = hsig.get((int(sl[k]), int(ix[k])))
                else: txc = ocost.get((int(sl[k]), int(ix[k]))); sig = osig.get((int(sl[k]), int(ix[k])))
                cul = ocul.get((int(sl[k]), int(ix[k]))) if ow[0] != "haqq" else None
                Lt = dict(who="248" if ow[0] == "haqq" else ow[0], mint=mint, mi=int(m), row=a + k, k=k, slot=int(sl[k]), idx=int(ix[k]), bt=int(bt[k]), cc=float(cc[k]),
                          cost=so[k] * (1 + fee[k]), sol_in=so[k], tok=tk[k], fee=fee[k], left=tk[k], out=0.0, sxc=0.0, txc_ok=txc is not None,
                          txc_buy=txc if txc is not None else (TXC_DEF if ow[0] == "haqq" else 0.0), sells=[], sig=sig, mayhem=mayhem, cs=cs,
                          age_slots=int(sl[k] - cs) if cs is not None else None, vsol_pre=float(vs[k - 1]) if k else v_c,
                          path=("ps" if cul == 120000 else "reg" if cul == 100000 else "other") if ow[0] != "haqq" else "248", day=L.day_of(int(bt[k])))
                # dump context
                lo5 = int(np.searchsorted(sl, sl[k] - 5)); lo10 = int(np.searchsorted(sl, sl[k] - 10))
                cand = [j for j in range(lo5, k) if not b[j] and outside[j]]
                dj = max(cand, key=lambda j: drop[j]) if cand else None
                mx10 = float(px[lo10:k].max()) if k > lo10 else pxp[k]
                Lt["dd10"] = float(1 - pxp[k] / mx10) if mx10 > 0 else 0.0
                Lt["px_pre"] = float(pxp[k])
                if dj is not None and drop[dj] > 0:
                    seller = int(u[dj])
                    bal = float(stok[:dj][u[:dj] == seller].sum())
                    cls = ("dev" if seller == cr else "bundler" if seller in bundl else "whale" if bal >= 0.06 * SUP else "early" if seller in early else "other")
                    btw = np.arange(dj + 1, k)
                    Lt.update(d_row=a + dj, d_k=dj, d_slot=int(sl[dj]), d_idx=int(ix[dj]), d_drop=float(drop[dj]), d_sol=float(so[dj]), d_pct=float(tk[dj] / SUP * 100),
                              d_user=seller, d_bal_pct=100 * bal / SUP, d_cls=cls, d_whale=bal >= 0.06 * SUP, d_slots=int(sl[k] - sl[dj]), d_ms=float(cc[k] - cc[dj]),
                              n_ahead=int(len(btw)), n_ahead_buy=int(b[btw].sum()), n_ahead_out=int((outside[btw]).sum()),
                              n_ahead_hq=int(hq[btw].sum()), n_ahead_us=int(own[btw].sum()),
                              px_vs_post=float(pxp[k] / px[dj]) if px[dj] > 0 else None, d_vpost=float(vs[dj]), d_bt=int(bt[dj]))
                    Lt["chunk"] = Lt["d_pct"] < 5.0 and 0.04 <= Lt["dd10"] <= 0.30
                else:
                    Lt.update(d_row=None, d_drop=0.0, d_slots=None, d_cls="none", chunk=False)
                Lt["dumpre"] = Lt["d_drop"] >= 0.05 and Lt["d_slots"] is not None and Lt["d_slots"] <= 2
                LOTS.append(Lt); Q[key].append(Lt)
            else:
                if ow[0] == "haqq": txc = hcost.get((int(sl[k]), int(ix[k]))); sig = hsig.get((int(sl[k]), int(ix[k])))
                else: txc = ocost.get((int(sl[k]), int(ix[k]))); sig = osig.get((int(sl[k]), int(ix[k])))
                if txc is None: txc = TXC_DEF if ow[0] == "haqq" else 0.0
                gross = so[k] * (1 - fee[k]); need = tk[k]; tot = tk[k]
                q = Q[key]
                while need > 0.5 and q:
                    Lt = q[0]; take = min(Lt["left"], need)
                    Lt["out"] += gross * take / tot; Lt["sxc"] += txc * take / tot; Lt["left"] -= take; need -= take
                    Lt["sells"].append((a + k, k, float(cc[k]), take / Lt["tok"], sig, int(sl[k]), int(ix[k])))
                    if Lt["left"] <= 0.5: q.popleft()
        for q in Q.values():
            for Lt in q:
                Lt["mark"] = Lt["left"] * px[-1] * (1 - 0.0125); Lt["open"] = True
        if n_m % 3000 == 0: print(f"  {n_m:,}/{len(um):,} mints, lots {len(LOTS):,} ({time.time() - t0:.0f}s)", flush=True)
    for Lt in LOTS:
        Lt.setdefault("mark", 0.0); Lt.setdefault("open", False)
        Lt["gross"] = Lt["out"] + Lt["mark"] - Lt["cost"]
        Lt["txc"] = Lt["txc_buy"] + Lt["sxc"]
        Lt["net"] = Lt["gross"] - Lt["txc"]
        Lt["close_cc"] = Lt["sells"][-1][2] if (Lt["sells"] and not Lt["open"]) else None
        Lt["hold_ms"] = Lt["close_cc"] - Lt["cc"] if Lt["close_cc"] else None
        Lt["first_sell_cc"] = Lt["sells"][0][2] if Lt["sells"] else None
    pickle.dump(dict(lots=LOTS, ofail=ofail, hfail=hfail, mints=um, st=st_, en=en_), open(f"{OUT}/v1.pkl", "wb"))
    c = collections.Counter((x["who"], x["path"]) for x in LOTS)
    print(dict(c))
    for w in ("248", "FRA", "AMS"):
        v = [x for x in LOTS if x["who"] == w]
        print(w, len(v), "net", round(sum(x["net"] for x in v), 3), "gross", round(sum(x["gross"] for x in v), 3), "txc", round(sum(x["txc"] for x in v), 3),
              "dumpre", sum(x["dumpre"] for x in v), "sig ok", sum(x["sig"] is not None for x in v))
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
