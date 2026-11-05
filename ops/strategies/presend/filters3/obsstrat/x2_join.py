#!/usr/bin/env python3
"""x2: one compact row per LIVE position r37..r42 (DEV+VAL): realized P&L (tail/pos_rNN.jsonl, read-only) + the observatory
hold tape (joined by our fill sig) + for re-arm positions the obs rearm_window of the same (mint, dump sig).
out: /home/moiz/sniper-data/filters3/obsstrat/pos_join.jsonl"""
import json, sys
TAIL = "/home/moiz/sniper-data/filters3/tail"
EXT = "/home/moiz/sniper-data/filters3/obsstrat/ext"
OUT = "/home/moiz/sniper-data/filters3/obsstrat/pos_join.jsonl"
CUT = 1793516400000000000  # 11-01 12:00 PKT
def cmp_tr(x):
    return [x["slot"], x["idx"], x.get("j", 0), x["t"], x["w"], 1 if x["buy"] else 0, x["sol"], x["tok"], x["vsol"], x["vtok"], x.get("fl", "")]
stats = {}
RUNS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["r37", "r38", "r39", "r40", "r41", "r42"]
if len(sys.argv) > 2: OUT = sys.argv[2]; TAIL = sys.argv[3]
o = open(OUT, "w")
for run in RUNS:
    hold, rw = {}, {}
    for line in open(f"{EXT}/{run}.obs_sel.jsonl"):
        d = json.loads(line)
        if d["ev"] == "hold_tape": hold[d["fill"]["sig"]] = d
        elif d["ev"] == "rearm_window": rw[(d["mint"], d["dump"]["sig"])] = d
    n = nh = nr = 0
    for line in open(f"{TAIL}/pos_{run}.jsonl"):
        p = json.loads(line); n += 1
        f, a = p["fill"], p.get("arm") or {}
        kind = f.get("kind") or a.get("kind") or "t2"
        h = hold.get(f["sig"]); nh += h is not None
        row = dict(run=run, per=("DEV" if p["t"] < CUT else "VAL") if run <= "r42" else "HOLD", w=p["w"], mint=p["mint"], kind=kind, pnl=p["pnl"], t=p["t"],
                   spend=a.get("spend") or f.get("spend"), sol_in=f["sol_in"], tokens=f["tokens"], fslot=f["slot"], fidx=f["idx"],
                   sat=f.get("slots_after_trigger"), path=f.get("path"), client=f.get("client"), ms_send_to_rx=f.get("ms_send_to_rx"),
                   close=p.get("close"), att=p.get("att"), arm_ann=a.get("ann"))
        tr0 = a.get("trig") or a.get("dump") or {}
        row["t0"] = tr0.get("t") or p["t"]
        sl = (p.get("close") or {}).get("sell_land")
        row["known"] = (sl[2] if sl and len(sl) > 2 and sl[2] else p["t"] + 3 * 10**9) + 2 * 10**9
        if kind == "rearm":
            row["dump"] = a.get("dump"); row["rholders"] = a.get("holders"); row["gap"] = a.get("gap")
            x = rw.get((p["mint"], (a.get("dump") or {}).get("sig")))
            if x is not None:
                nr += 1
                row["rw"] = {k: x.get(k) for k in ("r5_skip", "quiet", "holders", "others", "quiet_stop", "tries", "end", "arm", "superseded_live_t", "min_ratio")}
                c = (x.get("rows") or {}).get("c") or {}
                row["rw"]["c_hit"] = c.get("hit"); fc = c.get("fill") or {}
                row["rw"]["c_fill"] = {k: fc.get(k) for k in ("x", "px", "px_naive", "ms_after_arm", "slots_after_dump", "r2", "n_ahead", "followers", "second")} if fc else None
        else:
            row["trig"] = {k: (a.get("trig") or {}).get(k) for k in ("pct", "age_slots", "sol", "slot", "t", "wallet")}
            row["quiet"] = a.get("quiet"); row["v2"] = a.get("v2")
        if h is not None:
            row["h"] = dict(dump=h.get("dump"), exit=h.get("exit"), sells=h.get("sells"), hclose=h.get("close"), f1=h.get("first_1sol_sell"),
                            fb=h.get("first_big_sell"), fol=h.get("followers"), fill=h.get("fill"), tr=[cmp_tr(x) for x in h["trades"]])
        o.write(json.dumps(row) + "\n")
    stats[run] = (n, nh, nr); print(run, n, "hold", nh, "rearm_window", nr, flush=True)
