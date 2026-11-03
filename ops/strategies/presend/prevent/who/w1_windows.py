#!/usr/bin/env python3
"""WHO step 1 [MEASURED, read-only]: every LIVE pre-send window (T2 + re-arm) of the 20 live runs, and every SHADOW (paper) window of
the 9 shadow-only runs, with arm info, fill, realized P&L, failed-try fees, and the live tape (trades on the mint from our buy until
after our sell).
Out: /home/moiz/sniper-data/prevent/who/windows.pkl  (list of dicts)"""
import json, glob, pickle, collections, sys
from multiprocessing import Pool

OUT = "/home/moiz/sniper-data/prevent/who/windows.pkl"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
A = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r%s.jsonl"
F = "/home/moiz/sniper-data/runs/fra/runs/dip_r%s.jsonl"
LIVE = [("FRA", r, F % r) for r in (21, 22, 23, 24, 26, 27, 28)] + [("AMS", r, A % r) for r in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36, 37, 38)]
PAPER = [("AMS", r, A % r) for r in (14, 15, 21, 22, 23)] + [("FRA", r, F % r) for r in (15, 16, 20, 25)]


def one(args):
    reg, rn, fn, mode = args
    run = f"{reg}{rn}"
    ses = -1
    arms, fills, real, close, disarm, fee = {}, {}, {}, {}, {}, collections.Counter()
    natt = collections.Counter()
    tape = collections.defaultdict(list)
    parm, pfill, pexit = {}, {}, {}
    with open(fn, "rb") as fh:
        for raw in fh:
            if b'"ev":"presend' not in raw and b'"ev":"run_start"' not in raw: continue
            try: d = json.loads(raw)
            except Exception: continue
            e = d.get("ev")
            if e == "run_start": ses += 1; continue
            w = d.get("w")
            if mode == "live":
                if e == "presend_live_arm": arms[(ses, w)] = d
                elif e == "presend_live_fill": fills.setdefault((ses, w), d)
                elif e == "presend_live_realized": real[(ses, w)] = d
                elif e == "presend_live_close": close[(ses, w)] = d
                elif e == "presend_live_disarm": disarm[(ses, w)] = d
                elif e == "presend_live_tape": tape[(ses, d["mint"])].append((d["slot"], d.get("idx", 0), d["user"], bool(d["buy"]), d["sol"], d.get("tok", 0), d.get("vsol"), d.get("vtok"), d["t"]))
                elif e == "presend_attempt_land":
                    if d.get("res") != "ok": fee[(ses, w)] += d.get("fee", 0) or 0
                    natt[(ses, w)] += 1
            else:
                if e == "presend_arm": parm[(ses, w)] = d
                elif e == "presend_fill": pfill[(ses, w, d.get("row"))] = d
                elif e == "presend_exit": pexit[(ses, w, d.get("row"))] = d
    out = []
    if mode == "live":
        for k, a in arms.items():
            kind = a.get("kind") or "t2"
            fl = fills.get(k); r = real.get(k); c = close.get(k, {}); di = disarm.get(k, {})
            if kind == "rearm":
                dmp = a["dump"]; trig_slot = dmp["slot"]; wallet = dmp["seller"]; t_arm = dmp["t"] + (a.get("arm_ms_after_dump") or 0) * 1e6
                arm_slot = a.get("arm_slot") or a.get("check_slot"); age = dmp.get("age_slots"); pct = dmp.get("pct"); sol = dmp.get("sol"); trig_idx = dmp.get("idx")
            else:
                tg = a["trig"]; trig_slot = tg["slot"]; wallet = tg.get("wallet"); t_arm = tg["t"]; arm_slot = tg["slot"]; age = tg.get("age_slots"); pct = tg.get("pct"); sol = tg.get("sol"); trig_idx = tg.get("idx")
            mint = a.get("mint") or (a.get("trig") or {}).get("mint")
            W = dict(run=run, reg=reg, rn=rn, mode="live", ses=k[0], w=k[1], kind=kind, mint=mint, t_arm=t_arm / 1e9, trig_slot=trig_slot, trig_idx=trig_idx, arm_slot=arm_slot,
                     en_slot=a.get("en_slot"), wallet=wallet, pct=pct, sol=sol, age=age, holders=a.get("holders"), quiet_skip=a.get("quiet_skip"),
                     spend=a.get("spend"), fee_fail=fee.get(k, 0), n_att=natt.get(k, 0), attempts=di.get("attempts"), disarm_why=di.get("why"),
                     filled=fl is not None and r is not None)
            if fl is not None and r is not None:
                sl = (c.get("sell_land") or [None])[0]
                tp = [x for x in tape.get((k[0], mint), []) if x[0] >= fl["slot"] and (sl is None or x[0] <= sl + 1)]
                W.update(fill_slot=fl["slot"], fill_idx=fl.get("idx"), fill_t=fl["t"] / 1e9, pnl=r["pnl"] / 1e9, sol_in=fl.get("sol_in"), path=fl.get("path"),
                         client=fl.get("client"), sat=fl.get("slots_after_trigger"), p_sign=fl.get("p_sign"), p_pre=fl.get("p_entry_pre"), p_post=fl.get("p_entry_post"),
                         exit_why=c.get("exit_why"), sell_slot=sl, sell_idx=(c.get("sell_land") or [None, None])[1], tape=tp)
            out.append(W)
    else:
        for k, a in parm.items():
            rows = a.get("rows") or {}
            W = dict(run=run, reg=reg, rn=rn, mode="paper", ses=k[0], w=k[1], kind="t2", mint=a["mint"], t_arm=a["t"] / 1e9, trig_slot=a["slot"], trig_idx=a.get("idx"), arm_slot=a["slot"],
                     wallet=a.get("wallet"), pct=a.get("pct"), sol=a.get("sol"), age=a.get("age_slots"), rows=rows, quiet=a.get("quiet"))
            for row in ("a", "b", "c"):
                x = pexit.get((k[0], k[1], row)); f = pfill.get((k[0], k[1], row))
                if x is not None and f is not None:
                    W["fill_" + row] = dict(slot=f.get("m", {}).get("slot"), pnl=x.get("pnl"), net=x.get("net_cheap"), exit_slot=x.get("exit_slot"), why=x.get("why"),
                                            sol_in=(f.get("entry") or {}).get("sol_in"))
            out.append(W)
    return run, mode, out


if __name__ == "__main__":
    jobs = [(r, n, f, "live") for r, n, f in LIVE] + [(r, n, f, "paper") for r, n, f in PAPER]
    allw = []
    with Pool(6) as p:
        for run, mode, out in p.imap_unordered(one, jobs):
            nf = sum(1 for w in out if w.get("filled") or any(("fill_" + r) in w for r in "abc"))
            print(run, mode, "windows", len(out), "fills", nf, "pnl", round(sum(w.get("pnl", 0) or 0 for w in out), 3), flush=True)
            allw += out
    pickle.dump(allw, open(OUT, "wb"))
    print("total", len(allw))
