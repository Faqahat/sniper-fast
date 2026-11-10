#!/usr/bin/env python3
"""GUARDS step 8 [PAPER: engine shadow fills, no live fills]: the 9 shadow-only runs (AMS r14 r15 r21 r22 r23, FRA r15 r16 r20 r25).
The shadow's paper buy lands right after the crossing trade x (presend_fill "x"); guard A_Z (T2: the whale's balance after x <= Z x its
trigger balance) and B6a1 (the largest >= 6% holder at the trigger, other than the whale... and the whale itself) evaluated there on the
decoded tapes. DIRECT effect only (paper P&L of the blocked paper fills; no replacement). Rows a / c of the shadow; age >= 2 triggers only
(the live config since r37).
Also the LEAD lim085 (context limit 0.85 when another >= 6% holder is there): paper fills it would remove.
usage: g8_paper.py"""
import json, pickle, collections, sys, bisect
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/guards")
import glib as G
OUT = "/home/it/sniper-data/prevent/guards"
A = "/home/it/sniper-data/runs/ams/runs/dip_ams_r{}.jsonl"; F = "/home/it/sniper-data/runs/fra/runs/dip_r{}.jsonl"
RUNS = [("A" + str(r), A.format(r)) for r in (14, 15, 21, 22, 23)] + [("F" + str(r), F.format(r)) for r in (15, 16, 20, 25)]
fills = []
for name, fn in RUNS:
    ses = -1; arms = {}; fl = {}; ex = {}
    for raw in open(fn, "rb"):
        if b'"ev":"presend_arm"' not in raw and b'"ev":"presend_fill"' not in raw and b'"ev":"presend_exit"' not in raw and b'"ev":"run_start"' not in raw: continue
        r = json.loads(raw); e = r["ev"]
        if e == "run_start": ses += 1; continue
        ses = max(ses, 0)
        if e == "presend_arm": arms[(ses, r["w"])] = r
        elif e == "presend_fill": fl[(ses, r["w"], r["row"])] = r
        elif e == "presend_exit": ex[(ses, r["w"], r["row"])] = r
    for (s, w, row), f in fl.items():
        a = arms.get((s, w)); e = ex.get((s, w, row))
        if a is None or e is None or row not in ("a", "c"): continue
        if (a.get("age_slots") or 0) < 2: continue
        fills.append({"run": name, "row": row, "mint": f["mint"], "whale": a["wallet"], "bal": a["bal"], "trig": (a["slot"], a["idx"], a.get("j", 0)),
                      "x": (f["x"]["slot"], f["x"]["idx"], f["x"].get("j", 0)), "pnl": e["pnl"], "seller_is_whale": f.get("seller_is_whale"), "drop_pct": f.get("drop_pct")})
print("paper fills (age>=2, rows a+c)", len(fills), collections.Counter((f["run"], f["row"]) for f in fills))
tapes = G.load_tapes({f["mint"] for f in fills})
res = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0, 0.0]))
for f in fills:
    rows = tapes.get(f["mint"])
    if not rows: continue
    H = G.Hold(rows)
    K = H.key(*f["x"]) + 1        # just after the crossing trade
    KT = H.key(*f["trig"]) + 1
    wl = H.bal_before(f["whale"], K)
    hs = H.holders_before(KT, 0.06)
    top = max(hs.items(), key=lambda kv: kv[1])[0] if hs else None
    g = {"A_0.75": wl > 0.75 * f["bal"], "A_0.5": wl > 0.5 * f["bal"],
         "B6a1": bool(top) and H.bal_before(top, K) >= 0.06 * G.SUP,
         # LEAD (context limit 0.85): another >= 6% holder just before the crossing trade (~ the paper try's signing) and the paper fill's depth < 15%
         "lim085": any(u != f["whale"] for u in H.holders_before(H.key(*f["x"]), 0.06)) and (f["drop_pct"] or 99) < 15.0}
    for v, blk in g.items():
        c = res[(f["run"], f["row"])][v]
        c[0] += 1; c[1] += f["pnl"]
        if blk: c[2] += 1; c[3] += f["pnl"]
lines = ["PAPER (shadow) runs: per row, fills n / paper P&L SOL (shadow size) ; guard: blocked n / blocked P&L / gain = -blocked"]
for (run, row) in sorted(res):
    s = f"{run} row {row}: "
    for v, c in res[(run, row)].items():
        s += f"| {v}: {c[0]} fills {c[1]:+.3f}; blocked {c[2]} {c[3]:+.3f} -> gain {-c[3]:+.3f} "
    lines.append(s)
tot = collections.defaultdict(lambda: [0, 0.0, 0, 0.0])
for (run, row), d in res.items():
    for v, c in d.items():
        t = tot[(row, v)]
        for i in range(4): t[i] += c[i]
for k, c in sorted(tot.items()): lines.append(f"TOTAL row {k[0]} {k[1]}: fills {c[0]} {c[1]:+.3f}; blocked {c[2]} {c[3]:+.3f} -> gain {-c[3]:+.3f}")
open(f"{OUT}/paper.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
