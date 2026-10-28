#!/usr/bin/env python3
"""8yYMhu o1 (read-only): our live pre-send fills (FRA r27/r28, AMS r34 local records; AMS r35 events copied read-only from the AMS
server) -> one row per fill: mint, buy slot/idx, SOL in, tokens, sell slot/idx, SOL out, curve P&L, wallet-realized P&L (presend_live_realized).
Out: DATA/ours.pkl"""
import json, pickle, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as X
RUNS = {"FRA_r27": "/home/moiz/sniper-data/runs/fra/runs/dip_r27.jsonl", "FRA_r28": "/home/moiz/sniper-data/runs/fra/runs/dip_r28.jsonl",
        "AMS_r34": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r34.jsonl", "AMS_r35": f"{X.D}/ours/ams_r35_events.jsonl"}
rows = []
for run, f in RUNS.items():
    close = {}; real = {}; arm = {}
    for l in open(f, errors="ignore"):
        if '"presend_live_' not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        ev = d.get("ev")
        if ev == "presend_live_close": close[(d["mint"], d.get("pid"))] = d
        elif ev == "presend_live_realized": real[(d["mint"], d.get("pid"))] = d
        elif ev == "presend_live_arm": arm.setdefault(d["trig"]["mint"], []).append(d)
    for (m, pid), c in close.items():
        if c.get("result") != "sold" or not c.get("buys"): continue
        b = c["buys"][0]; sl = c.get("sell_land") or [None, None, None, None]
        r = real.get((m, pid), {})
        rows.append(dict(run=run, mint=m, pid=pid, s=b["slot"], i=b["idx"], t=b["t"] / 1e9, sol_in=sum(x["sol_in"] for x in c["buys"]) / 1e9,
                         cost=sum(x["cost"] for x in c["buys"]) / 1e9, tokens=sum(x["tokens"] for x in c["buys"]), n_buys=len(c["buys"]),
                         buy_sig=b["sig"], sell_s=sl[0], sell_i=sl[1], sol_out=(sl[3] / 1e9 if sl[3] else None), curve_pnl=c.get("curve_pnl", 0) / 1e9,
                         pnl=(r.get("pnl") / 1e9 if r.get("pnl") is not None else None), exit_why=c.get("exit_why"), held_s=c.get("held_s"),
                         sell_sig=(c.get("sell_sigs") or [[None]])[0][0], client=c.get("client"), path=c.get("path")))
pickle.dump(rows, open(f"{X.D}/ours.pkl", "wb"))
import collections
for run in RUNS:
    v = [r for r in rows if r["run"] == run]
    if v: print(run, len(v), X.pkt(min(r["t"] for r in v)), "->", X.pkt(max(r["t"] for r in v)), "realized %.4f" % sum(r["pnl"] or 0 for r in v), "curve %.4f" % sum(r["curve_pnl"] for r in v))
