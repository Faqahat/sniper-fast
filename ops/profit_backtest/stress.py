#!/usr/bin/env python3
"""Stress the best train-tuned config on VALIDATION under realistic fill degradation."""
import sys, os, json
sys.path.insert(0, "/root/profit_backtest")
import importlib

BEST_SEL = {"dev_min": 0.1, "dev_max": 1e9, "vanilla": True, "max_cosnipers": None, "max_creator_launches": 2}
BEST_EXIT = {"derisk_frac": 0.3, "ride_mult": 2.0, "trail_frac": 0.85, "cut_r": 0.8, "ladder_frac": 0.4, "cap_slots": 20}

def eval_val(slip, fee, emult):
    os.environ["SLIP"] = str(slip); os.environ["FEE_LEG"] = str(fee); os.environ["ENTRY_MULT"] = str(emult)
    import backtest
    importlib.reload(backtest)
    rows = sorted(backtest.ROWS, key=lambda r: r["create_slot"])
    cut = int(len(rows)*0.70); VAL = rows[cut:]
    REP = {}
    for c in backtest.CRE: REP[c["creator"]] = REP.get(c["creator"], 0)+1
    sel = {**BEST_SEL, "rep": REP}
    p = backtest.run(VAL, sel, BEST_EXIT); s = backtest.stats(p)
    srt = sorted(p, reverse=True)
    no2 = (sum(srt)-srt[0]-srt[1])/(len(srt)-2) if len(srt) > 2 else float("nan")
    return s, no2

print(f"{'slip':>5} {'fee/leg':>8} {'entryMx':>7} | {'n':>4} {'mean R':>8} {'med R':>7} {'win':>4} {'drop2 R':>8} {'SOL@2':>7}")
for slip, fee, emult, tag in [
    (0.08, 0.0008, 1.00, "optimistic (report base)"),
    (0.10, 0.003, 1.00, "moderate fees"),
    (0.12, 0.005, 1.05, "realistic snipe"),
    (0.12, 0.008, 1.10, "harsh fills+fees"),
    (0.15, 0.010, 1.15, "worst-case"),
]:
    s, no2 = eval_val(slip, fee, emult)
    print(f"{slip:>5} {fee:>8} {emult:>7} | {s['n']:>4} {s['mean']:>+8.4f} {s['median']:>+7.4f} {s['win']*100:>3.0f}% {no2:>+8.4f} {s['mean']*2:>+7.4f}   # {tag}")
