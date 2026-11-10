#!/usr/bin/env python3
"""Per-fill table from the live run records (read-only). One row per closed position (mint, pid).
Uses presend_live_{arm,fill,exit,sell_land,close,realized,tape} and the engine's dump records. Output fills_<run>.json."""
import json, sys, collections
RUNS = {"r28": "/home/it/sniper-data/runs/fra/runs/dip_r28.jsonl",
        "r34": "/home/it/sniper-data/runs/ams/runs/dip_ams_r34.jsonl",
        "r35": "/home/it/sniper-data/runs/ams/runs/dip_ams_r35.jsonl",
        "r36": "/home/it/sniper-data/presend_losses/raw/ams_r36.jsonl"}
OUT = "/home/it/sniper-data/presend_losses"
for run, path in RUNS.items():
    arms, fills, exits, sells, closes, real = {}, collections.defaultdict(list), {}, collections.defaultdict(list), {}, {}
    tape, dumps, start = collections.defaultdict(list), collections.defaultdict(list), None
    for l in open(path):
        try: d = json.loads(l)
        except Exception: continue
        e = d.get("ev")
        if e == "run_start": start = d
        elif e == "presend_live_arm": arms[(d["trig"]["mint"], d["w"])] = d
        elif e == "presend_live_fill" and not d.get("after_exit"): fills[(d["mint"], d["w"])].append(d)
        elif e == "presend_live_exit": exits.setdefault((d["mint"], d["pid"]), d)
        elif e == "presend_live_sell_land": sells[(d["mint"], d["pid"])].append(d)
        elif e == "presend_live_close": closes[(d["mint"], d["pid"])] = d
        elif e == "presend_live_realized": real[(d["mint"], d["pid"])] = d
        elif e == "presend_live_tape": tape[d["mint"]].append(d)
        elif e == "dump": dumps[d["mint"]].append(d)
    rows = []
    for (m, pid), c in closes.items():
        w = c["w"]; a = arms.get((m, w)); fl = fills.get((m, w), [])
        if not fl or (m, pid) not in real: continue
        f = fl[0]; ex = exits.get((m, pid), {}); sl = sells.get((m, pid), [])
        tr = sorted({(x["slot"], x["idx"], x.get("j", 0)): x for x in tape[m]}.values(), key=lambda x: (x["slot"], x["idx"], x.get("j", 0)))
        ours = set([b["sig"] for b in c.get("buys", [])] + [s[0] for s in c.get("sell_sigs", [])])
        # the dump that filled us: biggest drop record at or before our fill, within 2 slots
        dd = [x for x in dumps[m] if f["slot"] - 2 <= x["slot"] and (x["slot"], x["idx"]) < (f["slot"], f["idx"])]
        dmp = max(dd, key=lambda x: x["drop_pct"]) if dd else None
        rows.append(dict(run=run, mint=m, pid=pid, w=w, pnl=real[(m, pid)]["pnl"] / 1e9,
            spend=c.get("spend"), sol_in=c.get("sol_in_curve"), tokens=c.get("tokens"), curve_pnl=c.get("curve_pnl", 0) / 1e9,
            nbuys=len(c.get("buys", [])), rounds=c.get("rounds"), result=c.get("result"), tips=c.get("tips"),
            fill=dict(slot=f["slot"], idx=f["idx"], t=f["t"], client=f.get("client"), path=f.get("path"), ms_send_to_rx=f.get("ms_send_to_rx"),
                      slots_after_send=f.get("slots_after_send"), slots_after_trigger=f.get("slots_after_trigger"), p_pre=f.get("p_entry_pre"),
                      p_sign=f.get("p_sign"), lim=f.get("lim"), n=f.get("n"), tip=f.get("tip"), sig=f.get("sig")),
            fills_all=[dict(slot=x["slot"], idx=x["idx"], t=x["t"], sol_in=x.get("sol_in"), tokens=x.get("tokens")) for x in fl],
            exit=dict(slot=ex.get("slot"), t=ex.get("t"), why=ex.get("why")),
            sells=[dict(slot=s["slot"], idx=s["idx"], t=s["t"], sol=s["sol"], fee=s.get("fee")) for s in sl],
            arm=(dict(t=a["trig"]["t"], slot=a["trig"]["slot"], pct=a["trig"]["pct"], sol=a["trig"]["sol"] / 1e9, wallet=a["trig"]["wallet"],
                      age_slots=a["trig"]["age_slots"], vsol=a["trig"]["vsol"] / 1e9, quiet=a.get("quiet"), spend=a.get("spend")) if a else None),
            dump=(dict(slot=dmp["slot"], idx=dmp["idx"], t=dmp["t"], drop_pct=dmp["drop_pct"], sell=dmp["sell"], age=dmp["age"], dev=dmp.get("dev"),
                       vsol=dmp["vsol"] / 1e9, m2=dmp.get("m2")) if dmp else None),
            tape=[dict(slot=x["slot"], idx=x["idx"], t=x["t"], buy=x["buy"], sol=x["sol"], tok=x["tok"], vsol=x["vsol"], vtok=x["vtok"],
                       user=x["user"], ours=x["sig"] in ours) for x in tr]))
    json.dump(rows, open(f"{OUT}/fills_{run}.json", "w"))
    print(run, len(rows), "positions, pnl", round(sum(r["pnl"] for r in rows), 3), "spend", start["presend_live"].get("spend_sol", start["presend_live"].get("spend")) if start else None)
