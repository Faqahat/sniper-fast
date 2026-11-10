#!/usr/bin/env python3
"""BUNDLEWAL step 1 [MEASURED]: every live position (realized P&L) r37..r53 with its arm + fill context.
Out: /home/it/sniper-data/filters3/bundlewal/positions.jsonl
Row: run, w, mint, kind (t2|rearm), arm_slot (T2: trig.slot, trig idx; rearm: arm_slot), fill_slot, fill_t (s), pnl (SOL),
     split (DEV|VAL|HOLD), creator, eqgrp flag, f3 fresh."""
import json, os
OUT = "/home/it/sniper-data/filters3/bundlewal"
D = "/home/it/sniper-data"
SRC = {n: f"{D}/filters3/runs/r{n}.presend.jsonl" for n in range(37, 47)}
for n in (47, 48): SRC[n] = f"{D}/runs/ams/runs/dip_ams_r{n}.jsonl"
for n in range(49, 54): SRC[n] = f"{D}/runs/ams_r{n}/dip_ams_r{n}.jsonl"
VAL_T = 1793516400  # 2026-11-01 12:00 PKT
KEYS = ('"presend_live_arm"', '"presend_live_fill"', '"presend_live_realized"')

os.makedirs(OUT, exist_ok=True)
o = open(f"{OUT}/positions.jsonl", "w")
for n, f in SRC.items():
    arms, fills, rows = {}, {}, []
    for l in open(f, errors="replace"):
        if not any(k in l for k in KEYS): continue
        try: d = json.loads(l)
        except Exception: continue
        ev, w = d.get("ev"), d.get("w")
        if ev == "presend_live_arm":
            tr = d.get("trig")
            if tr:
                m, sl, ix, kind = tr["mint"], tr["slot"], tr.get("idx"), "t2"
            else:
                m, sl, ix, kind = d.get("mint"), d.get("arm_slot") or d.get("check_slot"), None, d.get("kind", "rearm")
            arms[(w, m)] = dict(kind=kind, arm_slot=sl, arm_idx=ix, creator=(d.get("ann") or {}).get("creator"),
                                eqflag=bool((d.get("eqgrp") or {}).get("flag")), fresh=(d.get("f3") or {}).get("fresh"),
                                wallet=(tr or {}).get("wallet") or (d.get("dump") or {}).get("seller"))
        elif ev == "presend_live_fill":
            k = (w, d["mint"])
            if k not in fills: fills[k] = dict(fill_slot=d.get("slot"), fill_t=d.get("t", 0) / 1e9)
        elif ev == "presend_live_realized":
            rows.append(d)
    miss = 0
    for d in rows:
        k = (d.get("w"), d["mint"]); a = arms.get(k); fl = fills.get(k)
        if not a or not fl: miss += 1; continue
        t = fl["fill_t"]
        split = "HOLD" if n >= 43 else ("VAL" if n == 42 and t >= VAL_T else "DEV")
        r = dict(run=n, w=d.get("w"), pid=d.get("pid"), mint=d["mint"], pnl=d["pnl"] / 1e9, split=split, **a, **fl)
        o.write(json.dumps(r) + "\n")
    print(f"r{n}: realized {len(rows)} matched {len(rows)-miss} miss {miss}", flush=True)
