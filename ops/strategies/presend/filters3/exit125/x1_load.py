#!/usr/bin/env python3
"""EXIT-125v200 step 1: join every live pre-send fill (r42..r50) with its exit, sell landing, realized P&L, ATA refund and hold tape.
Read-only on run data. Out: /home/it/sniper-data/filters3/exit125/fills.json (one record per fill).
Inputs are the event extracts ev_rNN.jsonl / ht_rNN.jsonl made by x0_extract.sh (grep of the run jsonl / obs files)."""
import json, collections
D = "/home/it/sniper-data/filters3/exit125"
RUNS = [42, 43, 44, 45, 46, 47, 48, 49, 50]
TIMER = {42: 200, 43: 200, 44: 200, 45: 200, 46: 200, 47: 200, 48: 125, 49: 125, 50: 200}   # log header "exit 2 slots or N ms"
SPEND = {42: 0.696, 43: 0.150, 44: 0.550, 45: 0.550, 46: 0.550, 47: 0.550, 48: 0.550, 49: 0.550, 50: 0.550}  # T2 spend per header
# run wall time (h) from first/last jsonl record; r50 = the partial local copy
HOURS = {42: 52.80, 43: 8.46, 44: 4.81, 45: 0.77, 46: 0.197, 47: 0.589, 48: 3.63, 49: 6.26, 50: 1.694}

out = []
for r in RUNS:
    tapes = {}
    try:
        for l in open(f"{D}/ht_r{r}.jsonl"):
            h = json.loads(l); tapes[h["fill"]["sig"]] = h
    except FileNotFoundError:
        pass
    pos = collections.defaultdict(list)   # mint -> list of open records (sequential, one position on)
    recs = []
    for l in open(f"{D}/ev_r{r}.jsonl"):
        o = json.loads(l); e = o["ev"]; m = o["mint"]
        if e == "presend_live_fill":
            x = dict(run=r, timer=TIMER[r], mint=m, sig=o["sig"], t=o["t"], slot=o["slot"], idx=o["idx"], tokens=o["tokens"],
                     sol_in=o["sol_in"], spend=(o.get("spend") or SPEND[r] * 1e9) / 1e9, kind=o.get("kind") or "t2",
                     client=o.get("client"), path=o.get("path"), exit=None, sells=[], realized=None, close=None, ata=None)
            recs.append(x); pos[m].append(x)
        else:
            if not pos[m]: continue
            x = pos[m][-1]
            if e == "presend_live_exit" and x["exit"] is None: x["exit"] = {k: o.get(k) for k in ("t", "slot", "why", "value", "slots_held")}
            elif e == "presend_live_sell_land": x["sells"].append({k: o.get(k) for k in ("t", "slot", "idx", "sol", "fee", "sig")})
            elif e == "presend_live_realized" and x["realized"] is None: x["realized"] = {k: o.get(k) for k in ("pnl", "buy_delta", "buy_fee", "sells_found", "buys_found", "src")}
            elif e == "presend_live_close" and x["close"] is None: x["close"] = {k: o.get(k) for k in ("sell_sigs", "exit_why", "result", "rounds", "merged", "curve_pnl", "spend", "sell_lands")}
            elif e == "presend_live_ata_close" and x["ata"] is None: x["ata"] = {k: o.get(k) for k in ("delta", "fee", "ok")}
    plt = collections.defaultdict(list)   # r50: no obs file locally -> the run jsonl's presend_live_tape rows (checked on r49: same trades)
    try:
        for l in open(f"{D}/plt_r{r}.jsonl"):
            o = json.loads(l); plt[o["mint"]].append(o)
    except FileNotFoundError:
        pass
    for x in recs:
        h = tapes.get(x["sig"])
        x["tape"] = h["trades"] if h else None
        x["tape_ms"] = 3000.0 if h else None
        x["tape_exit_ms"] = h["exit"]["ms_after_fill"] if h else None
        if not h and plt.get(x["mint"]):
            rows = [dict(o, w=o["user"][:8]) for o in plt[x["mint"]] if x["t"] - 1e9 < o["t"] < x["t"] + 5e9]
            if rows:
                x["tape"] = rows; x["tape_src"] = "jsonl presend_live_tape"
                x["tape_ms"] = (max(o["t"] for o in rows) - x["t"]) / 1e6   # covered only up to its last row
    out += recs
    print(f"r{r}: fills {len(recs)} with tape {sum(1 for x in recs if x['tape'])} with exit {sum(1 for x in recs if x['exit'])} "
          f"sells {collections.Counter(len(x['sells']) for x in recs)} realized {sum(1 for x in recs if x['realized'])} ata {sum(1 for x in recs if x['ata'])}")
json.dump(dict(fills=out, hours=HOURS, timer=TIMER), open(f"{D}/fills.json", "w"))
print("total", len(out))
