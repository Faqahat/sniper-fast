#!/usr/bin/env python3
"""LIM step 2 (read-only): counterfactual fill policies on OUR OWN live regular fires at their MEASURED landed position.
For each of the 1,546 regular fires (dv8/fires_tape.pkl: AMS r9-r33, FRA r1-r26) take the tape rows of the mint with both our
wallets removed, the dump row (jd) and our first landed copy (slot, idx). Our buy goes in before the first outside row after
our landed position (state = the row before). Tokens out there vs tokens at the post-dump state -> 'need' (tok_d / tok_pos);
the engine's min_out = tok_d / 1.05 (checked 99.7% on tape), so a policy 'guard g' fills iff need <= 1+g.
Exit: exact curve replay (dv8sim.pnl_exact: later buys keep SOL, later sells keep TOKENS), timer = last outside trade of
slot (our entry slot + h); h = the run's hold (5/6/19) ['ours'] and a grid 2..65 (haqq's exits are a per-lot slot timer).
Followers: fol 1.0 / 0.9 / 0.8 scales every outside BUY's SOL after our entry (the only modelled part).
Send-time features: dump drop %, dump SOL, curve SOL after the dump, token age, seller type, activity before the dump.
Out: data/lim/fires_cf.pkl"""
import json, pickle, sys, collections, time, os
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
HG = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 65]
FOL = [1.0, 0.9, 0.8]
SIZE = float(os.environ.get("LIM_SIZE", "0"))     # 0 = each fire's live spend; else a fixed size (e.g. haqq's 0.30)
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))


def main():
    t0 = time.time()
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[f["mint"]] for f in F if f["mint"] in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    ourid = np.array([idm[w] for w in L.WAL.values() if w in idm], np.uint32)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    need_m = {f["mint"] for f in F}
    CR = {m: CR[m] for m in need_m if m in CR}
    fbid = {idm[w] for w in FB if w in idm}
    print(f"loaded {len(TT):,} rows {time.time() - t0:.0f}s", flush=True)
    rows = []; skip = collections.Counter()
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: skip["nopos"] += 1; continue
        a, b = span[f["mint"]]; R = TT[a:b]
        R = R[~(np.isin(R["user"], ourid) | np.isin(R["signer"], ourid))]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        us_ = R["user"].astype(np.int64)
        dk = f["ds"] * 100000 + f["di"]; jd = np.flatnonzero(key == dk)
        if not len(jd): skip["nodump"] += 1; continue
        jd = int(jd[-1]); n = len(R)
        uk = f["us"][0] * 100000 + f["us"][1]
        r = int(np.searchsorted(key, uk))
        if r - 1 < jd: skip["before_dump"] += 1; continue
        size = SIZE or f["spend"]
        tok_d = S.entry_tokens(vs[jd], vt[jd], size); tok_p = S.entry_tokens(vs[r - 1], vt[r - 1], size)
        need = tok_d / tok_p
        pr = (vs[r - 1] / vt[r - 1]) / (vs[jd] / vt[jd])
        es = int(f["us"][0])
        pn = {}
        for h in sorted(set(HG + [f["hold"] or 5])):
            q = int(np.searchsorted(sl, es + h, side="right")) - 1
            q = max(q, r - 1)
            for fo in FOL:
                pn[(h, fo)] = S.pnl_exact(vs, vt, sol, tk, bu, r, q, size, fol=fo)
        # pre-buy price drop vs pre-dump state, send-time features
        vpre = vs[jd - 1] if jd >= 1 else None; tpre = vt[jd - 1] if jd >= 1 else None
        c = CR.get(f["mint"]) or {}
        cs = c.get("slot"); cr = c.get("creator")
        cr_id = idm.get(cr, -2) if cr else -2
        seller = int(us_[jd])
        bundl = set(us_[(sl == cs) & bu].tolist()) if cs is not None else set()
        early = set(us_[(sl <= cs + 10) & bu].tolist()) if cs is not None else set()
        stype = "dev" if seller == cr_id else "bundler" if seller in bundl else "fbot" if seller in fbid else "early" if seller in early else "other"
        w10 = (sl >= f["ds"] - 10) & (np.arange(n) < jd)
        same = (sl == f["ds"]) & (np.arange(n) < jd)
        btw = np.arange(jd + 1, r)
        rows.append(dict(run=f["run"], srv=f["srv"], t=f["t"], day=L.day_of(f["t"]), mint=f["mint"], out=f["out"], spend=size, hold=f["hold"] or 5,
                         need=need, pr=pr, n_ahead=r - 1 - jd, b_ahead=float(sol[btw][bu[btw]].sum()), nb_ahead=int(bu[btw].sum()),
                         nw_ahead=len(set(us_[btw][bu[btw]].tolist())), s_ahead=float(sol[btw][~bu[btw]].sum()),
                         d_slots=int(es - f["ds"]), d_ms=f.get("d_ms"), drop=1 - (vs[jd] / vt[jd]) / (vpre / tpre) if vpre else None,
                         dsol=float(sol[jd]), vpost=float(vs[jd]), age=(f["ds"] - cs) if cs is not None else None, stype=stype,
                         mayhem=bool(c.get("mayhem")), n10=int(w10.sum()), b10=float(sol[w10 & bu].sum()), s10=float(sol[w10 & ~bu].sum()),
                         nsame=int(same.sum()), bsame=float(sol[same & bu].sum()), buy_cost=f["buy_cost"], realized=f["realized"],
                         client=f["land_client"], dclient=f["dump_client"], near=f["land_near"], pn=pn, us=f["us"], ds=f["ds"]))
    print("rows", len(rows), "skipped", dict(skip), f"{time.time() - t0:.0f}s", flush=True)
    pickle.dump(rows, open(f"{OUT}/fires_cf" + (f"_s{SIZE:g}" if SIZE else "") + ".pkl", "wb"))


if __name__ == "__main__":
    main()
