#!/usr/bin/env python3
"""LIM step 16 (read-only): SELECTIVE loosening at OUR MEASURED landed positions - data build.
Events:
  reg : our 1,544 live regular fires (dv8 fires_tape). Dump = the trigger sell (ds, di). One candidate entry = our first landed copy.
  ps  : our live pre-send windows (l8 grouping; tries with res 6042/ok, landed, on tape). Per try: need = min_out / tokens at its
        landed state; 'crossed' = an outside trade after the try's send slot and before its landing put the price below the try's
        real limit; the try's dump = the LAST such crossing row before it (the sell it would be reacting to).
Selection flags per dump (all keyed on the dump row):
  oracle  : a haqq bot-247/248 buy (pos/p1.pkl lot codes) landed on the mint after the dump and within dump slot + 2 (MEASURED, hindsight)
  hsel    : analyst H's f10 selector passed (score >= thr) at a checkpoint of the whale episode whose dump is this row
            (follow/decisions.jsonl 'score' lines; test days only; causal by construction)
  scored  : that episode was scored at all (coverage)
  wh_n, wh_ide : seller's book dumps (follow/bookdumps.npz) closed (slot+3) before the dump slot within 24 h: count, mean 2-slot
            ideal value of a 0.40 SOL buy after them (H's top feature wh_ide24), causal
  s_cr / s_cs : seller is the token's creator / bought in the creation slot (causal)
Values per candidate entry (exact replay, both our wallets removed, fol 1.0/0.9/0.8):
  tm  = timer exit (reg: last outside trade of slot entry+hold; ps: entry+2)
  wv  = wave exit RIDE(150 ms, 150 ms gap, 700 ms cap) with our MEASURED reactive sell delays (exit analyst xsim / x12)
Also per candidate: ideal = the same values for a buy right AFTER the dump row (the best possible position), dslots / nahead =
our landing slot minus the dump slot / outside rows between the dump and us.
Out: data/lim/sel_events.pkl"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import dv8lib as L, dv8sim as S
from xsim import Pos
from x12_wave import ev as wave_ev
from x7_ourexits import delays
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"; HD = "/home/moiz/sniper-data/haqq_dissect"
FOLS = (1.0, 0.9, 0.8); WAVE = ("RIDE", 150, 150, 700); HZ = 40


def main():
    t0 = time.time()
    DR, DT, _ = delays()
    ids, idm = L.ids_map()
    ourid = np.array([idm[w] for w in L.WAL.values() if w in idm], np.uint32)
    F = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    PR = [p for p in pickle.load(open(f"{L.D}/live_presend.pkl", "rb")) if not p.get("dry") and p.get("tape") and p["res"] in ("6042", "ok")]
    mints = {f["mint"] for f in F} | {p["mint"] for p in PR}
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[m] for m in mints if m in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)]); TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    TT = TT[~(np.isin(TT["user"], ourid) | np.isin(TT["signer"], ourid))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    CCall = L.cc(TT["slot"], TT["idx"])
    CR = json.load(open(f"{L.TAB}/creates.json")); CR = {m: CR[m] for m in mints if m in CR}
    print(f"tape {len(TT):,} rows ({time.time() - t0:.0f}s)", flush=True)
    # ---- oracle: bot 247/248 buys
    P1 = pickle.load(open(f"{HD}/pos/p1.pkl", "rb"))
    BOT = collections.defaultdict(list)
    for b, lt in zip(P1["buys"], P1["lots"]):
        if lt.get("code") in (247, 248): BOT[b["mint"]].append((b["slot"], b["idx"]))
    BOT = {m: sorted(v) for m, v in BOT.items()}
    # ---- H selector
    hsel, hsc = set(), set()
    with open(f"{HD}/follow/decisions.jsonl") as fh:
        for l in fh:
            if not l.startswith('{"kind": "score"'): continue
            d = json.loads(l)
            if d.get("dump_slot") is None: continue
            k = (d["mint"], d["dump_slot"], d["dump_idx"]); hsc.add(k)
            if d.get("pass_") or d.get("arms"): hsel.add(k)
    print(f"H scored dumps {len(hsc):,}, passed {len(hsel):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---- seller history: book dumps (follow tape rows -> user, slot, bt)
    B = np.load(f"{HD}/follow/bookdumps.npz"); FT = np.load(f"{HD}/follow/tape.npy", mmap_mode="r")
    br = B["row"]; bu_ = np.asarray(FT["user"][br]).astype(np.int64); bsl = np.asarray(FT["slot"][br]).astype(np.int64); bbt = np.asarray(FT["bt"][br]).astype(np.int64)
    ok = ~np.isnan(B["ide"])
    o = np.lexsort((bsl, bu_)); o = o[ok[o]]
    HS = {}
    uu, s0 = np.unique(bu_[o], return_index=True); e0 = np.append(s0[1:], len(o))
    for u, a, b in zip(uu.tolist(), s0, e0):
        oo = o[a:b]; HS[u] = (bsl[oo] + 3, bbt[oo], B["ide"][oo])
    print(f"book dumps {len(br):,}, sellers {len(HS):,} ({time.time() - t0:.0f}s)", flush=True)

    def sel_flags(mint, k, R, sl, ix, us, bu, cs, cr_id, bundl):
        ds, di = int(sl[k]), int(ix[k]); u = int(us[k]); bt = int(R["bt"][k])
        bb = BOT.get(mint, [])
        orc = any((s, i) > (ds, di) and s <= ds + 2 for s, i in bb)
        h = HS.get(u); n = 0; ide = np.nan
        if h is not None:
            m = (h[0] < ds) & (h[1] > bt - 86400); n = int(m.sum()); ide = float(h[2][m].mean()) if n else np.nan
        return dict(d_slot=ds, d_idx=di, seller=u, oracle=orc, hsel=(mint, ds, di) in hsel, scored=(mint, ds, di) in hsc,
                    wh_n=n, wh_ide=ide, s_cr=(u == cr_id), s_cs=(u in bundl), d_drop=None)

    def values(R, a, r, size, sl, ix, vs, vt, sol, tk, bu, hold):
        es = int(sl[r - 1]) if False else None
        out = {}
        return out

    EV = []
    def entry_vals(R, ccr, sl, ix, vs, vt, sol, tk, bu, fee, r, us_slot, us_idx, size, hold):
        v = {}
        q = max(int(np.searchsorted(sl, us_slot + hold, side="right")) - 1, r - 1)
        hi = int(np.searchsorted(sl, us_slot + HZ, side="right"))
        cc0 = float(L.cc(us_slot, us_idx))
        p = dict(dcc=(ccr[r:hi] - cc0).astype(np.float64), bu=bu[r:hi].copy(), so=sol[r:hi].copy(), tk=tk[r:hi].copy(),
                 V0=float(vs[r - 1]), T0=float(vt[r - 1]), sin=size / (1 + S.FEE), cost=size, fee=S.FEE, off_in_slot=cc0 - us_slot * L.SMS)
        for fo in FOLS:
            v[("tm", fo)] = S.pnl_exact(vs, vt, sol, tk, bu, r, q, size, fol=fo)
            P_ = Pos(p, fo); v[("wv", fo)] = (wave_ev(P_, WAVE, DR, DT) - 1) * size if P_.n else (P_.v_pre - 1) * size
        return v

    # ---------------- regular fires
    for f in F:
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: continue
        a, b = span[f["mint"]]; R = TT[a:b]; ccr = CCall[a:b]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        us = R["user"].astype(np.int64)
        jd = np.flatnonzero(key == f["ds"] * 100000 + f["di"])
        if not len(jd): continue
        jd = int(jd[-1]); r = int(np.searchsorted(key, f["us"][0] * 100000 + f["us"][1]))
        if r - 1 < jd: continue
        c = CR.get(f["mint"]) or {}; cs = c.get("slot"); cr_id = idm.get(c.get("creator"), -2) if c.get("creator") else -2
        bundl = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
        size = f["spend"]; tok_d = S.entry_tokens(vs[jd], vt[jd], size); tok_p = S.entry_tokens(vs[r - 1], vt[r - 1], size)
        e = dict(kind="reg", run=f["run"], srv=f["srv"], day=L.day_of(f["t"]), mint=f["mint"], live_fill=f["out"] == "fill", mayhem=bool(c.get("mayhem")),
                 cands=[dict(need=tok_d / tok_p, ok=f["out"] == "fill", crossed=True, dump=sel_flags(f["mint"], jd, R, sl, ix, us, bu, cs, cr_id, bundl),
                             val=entry_vals(R, ccr, sl, ix, vs, vt, sol, tk, bu, None, r, f["us"][0], f["us"][1], size, f["hold"] or 5))])
        e["cands"][0]["dump"]["d_drop"] = float(1 - (vs[jd] / vt[jd]) / (vs[jd - 1] / vt[jd - 1])) if jd else None
        e["cands"][0].update(dslots=int(f["us"][0] - sl[jd]), nahead=int(r - 1 - jd),
                             ideal=entry_vals(R, ccr, sl, ix, vs, vt, sol, tk, bu, None, jd + 1, int(sl[jd]), int(ix[jd]), size, f["hold"] or 5))
        EV.append(e)
    print(f"reg events {len(EV)} ({time.time() - t0:.0f}s)", flush=True)
    # ---------------- pre-send windows
    by = collections.defaultdict(list)
    for p in PR: by[(p["run"], p["mint"])].append(p)
    nps = 0
    for (run, mint), v in by.items():
        if mint not in span: continue
        a, b = span[mint]; R = TT[a:b]; ccr = CCall[a:b]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        us = R["user"].astype(np.int64)
        c = CR.get(mint) or {}; cs = c.get("slot"); cr_id = idm.get(c.get("creator"), -2) if c.get("creator") else -2
        bundl = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
        v.sort(key=lambda p: (p["send_slot"] or 0))
        wins = []; cur = []
        for p in v:
            if cur and (p["send_slot"] or 0) - (cur[-1]["send_slot"] or 0) > 20: wins.append(cur); cur = []
            cur.append(p)
        if cur: wins.append(cur)
        for w in wins:
            tr = []
            for p in w:
                s_, i_, okk = p["tape"]; r = int(np.searchsorted(key, s_ * 100000 + i_))
                if r < 1: continue
                size = p["spend"] / 1e9; sn = size / (1 + S.FEE)
                tokp = S.entry_tokens(vs[r - 1], vt[r - 1], size)
                lo = int(np.searchsorted(sl, p["send_slot"] or s_))
                cj = None
                if r - 1 >= lo:
                    tt = vt[lo:r]; vv = vs[lo:r]
                    hit = np.flatnonzero((tt - vv * tt / (vv + sn)) >= p["min_out"])
                    if len(hit): cj = lo + int(hit[-1])
                tr.append(dict(key=s_ * 100000 + i_, r=r, slot=s_, idx=i_, need=p["min_out"] / tokp, ok=okk, cj=cj, size=size, t=p["t"]))
            if not tr: continue
            tr.sort(key=lambda x: x["key"])
            cands = []; ncross = 0; idc = {}
            for x in tr:
                if not (x["ok"] or x["cj"] is not None): continue
                if x["cj"] is not None: ncross += 1
                if ncross > 40 and not x["ok"]: continue
                d = sel_flags(mint, x["cj"], R, sl, ix, us, bu, cs, cr_id, bundl) if x["cj"] is not None else None
                if d is not None and x["cj"] >= 1: d["d_drop"] = float(1 - (vs[x["cj"]] / vt[x["cj"]]) / (vs[x["cj"] - 1] / vt[x["cj"] - 1]))
                ideal = None
                if x["cj"] is not None:
                    if x["cj"] not in idc: idc[x["cj"]] = entry_vals(R, ccr, sl, ix, vs, vt, sol, tk, bu, None, x["cj"] + 1, int(sl[x["cj"]]), int(ix[x["cj"]]), x["size"], 2)
                    ideal = idc[x["cj"]]
                cands.append(dict(need=x["need"], ok=x["ok"], crossed=x["cj"] is not None, dump=d, ideal=ideal,
                                  dslots=(x["slot"] - int(sl[x["cj"]])) if x["cj"] is not None else None, nahead=(x["r"] - 1 - x["cj"]) if x["cj"] is not None else None,
                                  val=entry_vals(R, ccr, sl, ix, vs, vt, sol, tk, bu, None, x["r"], x["slot"], x["idx"], x["size"], 2)))
            EV.append(dict(kind="ps", run=run, srv=run[:3], day=L.day_of(tr[0]["t"]), mint=mint, live_fill=any(x["ok"] for x in tr),
                           mayhem=bool(c.get("mayhem")), cands=cands, ntries=len(tr)))
            nps += 1
    print(f"ps windows {nps} ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(EV, open(f"{OUT}/sel_events.pkl", "wb"))


if __name__ == "__main__":
    main()
