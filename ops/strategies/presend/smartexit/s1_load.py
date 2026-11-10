#!/usr/bin/env python3
"""SMARTEXIT step 1: one record per live pre-send fill r37..r55 = fill + exit + sell landing(s) + realized + ATA refund + hold tape
+ arm context (last presend_live_arm on the mint before the fill) + split label.  Read-only on run data.
Generalises filters3/exit125/x1_load.py (same joins) to every run.  Out: /home/it/sniper-data/smartexit/fills.json"""
import json, collections, os, calendar
O = "/home/it/sniper-data/smartexit"; E = f"{O}/ev"
R = "/home/it/sniper-data/runs"
S55 = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/r55"
RUNS = list(range(37, 56))
DEV_CUT = calendar.timegm((2026, 11, 1, 7, 0, 0)) * 10**9      # 2026-11-01 12:00 PKT
HDR_SPEND = {r: 0.696 for r in range(37, 43)} | {43: 0.150} | {r: 0.55 for r in range(44, 55)} | {55: 0.69}

def jsonl_of(r):
    if r <= 48: return f"{R}/ams/runs/dip_ams_r{r}.jsonl"
    if r <= 54: return f"{R}/ams_r{r}/dip_ams_r{r}.jsonl"
    return f"{S55}/dip_ams_r55.jsonl"

def first_last_t(fn):
    import re
    pat = re.compile(rb'"t":(\d{19})')
    with open(fn, "rb") as f:
        t0 = None
        for _ in range(200):
            m = pat.search(f.readline())
            if m: t0 = int(m.group(1)); break
        f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - 2_000_000))
        t1 = max(int(m.group(1)) for m in pat.finditer(f.read()))
    return t0, t1

def split_of(r, t):
    if r <= 41: return "dev"
    if r == 42: return "dev" if t < DEV_CUT else "val"
    return "hold"

out = []; span = {}
for r in RUNS:
    t0, t1 = first_last_t(jsonl_of(r)); span[r] = (t0, t1)
    tapes = {}
    for l in open(f"{E}/ht_r{r}.jsonl"):
        h = json.loads(l); tapes.setdefault(h["fill"]["sig"], h)
    pos = collections.defaultdict(list); last_arm = {}; recs = []
    for l in open(f"{E}/ev_r{r}.jsonl"):
        o = json.loads(l); e = o["ev"]
        if e == "presend_live_arm":
            m = o.get("mint") or (o.get("trig") or {}).get("mint")
            last_arm[m] = o; continue
        m = o["mint"]
        if e == "presend_live_fill":
            a = last_arm.get(m)
            sp = (o.get("spend") or (a or {}).get("spend") or HDR_SPEND[r] * 1e9) / 1e9
            x = dict(run=r, mint=m, sig=o["sig"], t=o["t"], slot=o["slot"], idx=o["idx"], tokens=o["tokens"], sol_in=o["sol_in"],
                     spend=sp, kind=o.get("kind") or ("rearm" if (a or {}).get("kind") == "rearm" else "t2"), client=o.get("client"),
                     path=o.get("path"), tip=o.get("tip"), slots_after_trigger=o.get("slots_after_trigger"), fann=o.get("ann"),
                     arm={k: (a or {}).get(k) for k in ("trig", "drop", "k", "nb", "ann", "f3", "q4", "quiet", "v2", "eqgrp", "kind", "spend", "en_slot")},
                     exit=None, sells=[], realized=None, close=None, ata=None, split=split_of(r, o["t"]))
            recs.append(x); pos[m].append(x)
        else:
            if not pos[m]: continue
            x = pos[m][-1]
            if e == "presend_live_exit" and x["exit"] is None: x["exit"] = {k: o.get(k) for k in ("t", "slot", "why", "value", "slots_held")}
            elif e == "presend_live_sell_land": x["sells"].append({k: o.get(k) for k in ("t", "slot", "idx", "sol", "fee", "sig")})
            elif e == "presend_live_realized" and x["realized"] is None: x["realized"] = {k: o.get(k) for k in ("pnl", "buy_delta", "buy_fee", "sells_found", "buys_found", "src")}
            elif e == "presend_live_close" and x["close"] is None: x["close"] = {k: o.get(k) for k in ("sell_sigs", "exit_why", "result", "rounds", "merged", "curve_pnl", "spend", "sell_lands", "tips")}
            elif e == "presend_live_ata_close" and x["ata"] is None: x["ata"] = {k: o.get(k) for k in ("delta", "fee", "ok")}
    for x in recs:
        h = tapes.get(x["sig"])
        x["tape"] = h["trades"] if h else None
        x["dump"] = h.get("dump") if h else None
        x["followers"] = h.get("followers") if h else None
    out += recs
    print(f"r{r}: fills {len(recs)} tape {sum(1 for x in recs if x['tape'])} exit {sum(1 for x in recs if x['exit'])} "
          f"sells {dict(collections.Counter(len(x['sells']) for x in recs))} realized {sum(1 for x in recs if x['realized'])} "
          f"kinds {dict(collections.Counter(x['kind'] for x in recs))} spend {dict(collections.Counter(round(x['spend'],3) for x in recs))} "
          f"hours {(t1 - t0) / 3.6e12:.2f}")
hours = {"dev": 0.0, "val": 0.0, "hold": 0.0}; run_hours = {}
for r, (t0, t1) in span.items():
    run_hours[r] = (t1 - t0) / 3.6e12
    if r <= 41: hours["dev"] += run_hours[r]
    elif r == 42: hours["dev"] += (DEV_CUT - t0) / 3.6e12; hours["val"] += (t1 - DEV_CUT) / 3.6e12
    else: hours["hold"] += run_hours[r]
json.dump(dict(fills=out, run_hours=run_hours, split_hours=hours), open(f"{O}/fills.json", "w"))
print("total", len(out), "split hours", {k: round(v, 2) for k, v in hours.items()},
      "fills/split", dict(collections.Counter(x["split"] for x in out)))
