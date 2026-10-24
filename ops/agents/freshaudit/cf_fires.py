#!/usr/bin/env python3
# counterfactuals on our 69 fires: validation (actual fills), guard widths, earlier landing
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from sim import *
TP = load_tapes("/home/moiz/sniper/ops/agents/freshaudit/out/tapes_live.json.gz")
FC = json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/fire_chain.json"))
TT = {r["mint"] + str(r.get("di")): r for r in json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/tape_timing.json"))}
res = []
for f in FC:
    if "ours" not in f or "dump" not in f: continue
    m = f["mint"]; rows = TP.get(m)
    if not rows: print("no tape", m); continue
    tr = trades(rows, drop_user=OURS)
    allt = trades(rows)
    d = f["dump"]; o = f["ours"]
    # post-dump state from the dump event itself
    dst = None
    for t in allt:
        if (t[0], t[1]) == (d["s"], d["i"]) and t[3] == 0: dst = (t[7], t[8]); fb, cb = t[9], t[10]
    if dst is None: print("no dump state", m); continue
    fr = (fb + cb) / 1e4
    B = f["spend"] / 1e9; tip = f["tips"]
    tpsl = f["run"] <= 4
    ex = ("tpsl", 5, 100, 100) if tpsl else ("time", 5, 100)
    act = simulate(tr, (o["s"], o["i"]), dst, B, guard=1.05, exit_mode=ex, fr=fr, tip=tip)
    # validation for fills: exact sell position
    val = None
    if f["result"] == "sold" and f.get("sell_land"):
        sp = tuple(f["sell_land"][:2])
        exact = simulate(tr, (o["s"], o["i"]), dst, B, guard=None, exit_mode=("time", sp[0] - o["s"], sp[1]), fr=fr, tip=tip)
        val = (exact["pnl_curve"], f["curve_pnl"] / 1e9)
    rec = dict(run=f["run"], mint=m, res=f["result"], B=B, fr=fr, act_fill=act and act["fill"], act_ratio=act and act["entry_ratio"], val=val)
    for g in (1.05, 1.10, 1.15, 1.25, None):
        for nm, mode in (("time", ("time", 5, 100)), ("tpsl", ("tpsl", 5, 100, 100))):
            r = simulate(tr, (o["s"], o["i"]), dst, B, guard=g, exit_mode=mode, fr=fr, tip=tip)
            rec[f"g{g}_{nm}"] = r and (r["fill"], round(r["pnl_net"], 5))
    # landing right after the dump (first in line), and right after the dump in the next slot
    for nm, pos in (("first", (d["s"], d["i"] + 1)), ("next0", (d["s"] + 1, 0))):
        r = simulate(tr, pos, dst, B, guard=1.05, exit_mode=("time", 5, 100), fr=fr, tip=tip)
        rec[f"{nm}_time"] = r and (r["fill"], round(r["pnl_net"], 5), round(r["entry_ratio"], 4))
        r = simulate(tr, pos, dst, B, guard=1.05, exit_mode=("tpsl", 5, 100, 100), fr=fr, tip=tip)
        rec[f"{nm}_tpsl"] = r and (r["fill"], round(r["pnl_net"], 5))
    res.append(rec)
json.dump(res, open("/home/moiz/sniper/ops/agents/freshaudit/out/cf_fires.json", "w"))
print("validation (sim curve pnl vs actual curve pnl, SOL):")
for r in res:
    if r["val"]: print(f"  {r['mint'][:6]} sim={r['val'][0]:+.5f} act={r['val'][1]:+.5f} diff={r['val'][0]-r['val'][1]:+.5f}")
print("act fill model agrees with reality:", sum(1 for r in res if (r["act_fill"] and r["res"] == "sold") or (r["act_fill"] is False and r["res"] == "buy_failed")), "of", len(res))
for r in res:
    if (r["act_fill"] and r["res"] != "sold") or (r["act_fill"] is False and r["res"] == "sold"): print("  disagree:", r["mint"][:6], r["res"], r["act_ratio"])
def summ(key, subset):
    xs = [r[key] for r in subset if r.get(key)]
    n = len(xs); fills = sum(1 for x in xs if x[0]); pnl = sum(x[1] for x in xs)
    return f"{key:<16} n={n} fills={fills} net={pnl:+.4f} SOL  per-fire={pnl/max(1,n):+.5f}"
for nm, sub in (("ALL fires", res), ("actually FILLED", [r for r in res if r["res"] == "sold"]), ("actually FAILED", [r for r in res if r["res"] != "sold"])):
    print("\n==", nm, len(sub))
    for k in ("g1.05_time", "g1.05_tpsl", "g1.1_time", "g1.1_tpsl", "g1.15_time", "g1.15_tpsl", "g1.25_time", "g1.25_tpsl", "gNone_time", "gNone_tpsl", "first_time", "first_tpsl", "next0_time", "next0_tpsl"):
        print("  ", summ(k, sub))
