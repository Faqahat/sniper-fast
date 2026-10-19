#!/usr/bin/env python3
"""Full deliverable: baseline, staged train/val grid search, tail sensitivity, REPORT.md."""
import sys, os, json, statistics as st, itertools
sys.path.insert(0, "/root/profit_backtest")
import backtest as B
from backtest import ROWS, run, stats, SLIP, FEE_LEG, SIZE

# creator reputation from the in-sample stream (launch frequency per creator) -- caveat: sample-only
REP = {}
for c in B.CRE:
    REP[c["creator"]] = REP.get(c["creator"], 0) + 1

# train/val split by time (create_slot)
rows = sorted(ROWS, key=lambda r: r["create_slot"])
cut = int(len(rows)*0.70)
TRAIN, VAL = rows[:cut], rows[cut:]
split_slot = TRAIN[-1]["create_slot"]

BASE_EXIT = {"derisk_frac": 0.40, "ride_mult": 1.6, "trail_frac": 0.85, "cut_r": 0.85, "ladder_frac": 0.30, "cap_slots": 20}
BASE_FILT = {"dev_min": 0.3, "dev_max": 1e9, "vanilla": False}

def line(s):
    return (f"n={s['n']} mean={s['mean']:+.4f} med={s['median']:+.4f} win={s['win']*100:.0f}% "
            f"sd={s['sd']:.3f} sharpe={s['sharpe']:.3f} tot={s['tot']:+.2f} top5%={s['top5_share']*100:.0f}%")

out = []
def P(*a):
    msg = " ".join(str(x) for x in a); print(msg); out.append(msg)

P(f"# Profit backtest report")
P(f"Sample: {len(ROWS)} unbiased pump.fun create_v2 launches with usable create-slot price series.")
P(f"Assumptions: flat slippage {SLIP*100:.0f}%/leg, fees {FEE_LEG} SOL/leg at size {SIZE} SOL, same-slot fill at create-slot floor px.")
P(f"Returns are per-snipe net fraction of size (R). SOL expectancy = R * size.")
P(f"Train/val split by slot: train={len(TRAIN)} val={len(VAL)} (split at slot {split_slot}).\n")

# ---------- A. BASELINE ----------
full = run(ROWS, BASE_FILT, BASE_EXIT); S = stats(full)
P("## A. BASELINE — current config (min_dev_buy=0.3, is_snipeable, derisk .40 ride 1.6 trail .85 cut .85 ladder .30 cap 8s)")
P("FULL  ", line(S))
P(f"  passed filter: {S['n']}/{len(ROWS)} ({S['n']/len(ROWS)*100:.0f}%)")
P(f"  dist R: p10={S['p10']:+.3f} p25={S['p25']:+.3f} p50={S['p50']:+.3f} p75={S['p75']:+.3f} p90={S['p90']:+.3f} p99={S['p99']:+.3f}")
P(f"  SOL expectancy @ {SIZE} SOL: mean={S['mean']*SIZE:+.4f}  median={S['median']*SIZE:+.4f}")
sval = stats(run(VAL, BASE_FILT, BASE_EXIT)); strn = stats(run(TRAIN, BASE_FILT, BASE_EXIT))
P("TRAIN ", line(strn)); P("VAL   ", line(sval))
# tail sensitivity on full baseline
srt = sorted(full, reverse=True)
if len(srt) > 2:
    no1 = (sum(srt)-srt[0])/(len(srt)-1); no2 = (sum(srt)-srt[0]-srt[1])/(len(srt)-2)
    P(f"  tail check: mean={S['mean']:+.4f}  drop top1={no1:+.4f}  drop top2={no2:+.4f}  (top1 R={srt[0]:+.2f} top2 R={srt[1]:+.2f})\n")

# ---------- B. GRID SEARCH (staged, train-tuned) ----------
P("## B. Grid search (train-tuned, validated out-of-sample)")

# Stage 1: selection with base exit, on TRAIN
sel_grid = []
for dev_min in [0.0, 0.1, 0.3, 0.5, 1.0, 2.0]:
    for dev_max in [1e9, 3.0, 1.5, 1.0]:
        if dev_max <= dev_min: continue
        for vanilla in [False, True]:
            for maxco in [None, 2]:
                for maxrep in [None, 2]:
                    sel_grid.append({"dev_min": dev_min, "dev_max": dev_max, "vanilla": vanilla,
                                     "max_cosnipers": maxco, "max_creator_launches": maxrep, "rep": REP})
sel_res = []
for f in sel_grid:
    p = run(TRAIN, f, BASE_EXIT); s = stats(p)
    if s and s["n"] >= 40: sel_res.append((s["mean"], f, s))
sel_res.sort(reverse=True, key=lambda x: x[0])
P(f"\nStage 1 — top selection filters on TRAIN (base exit, n>=40), with VAL check:")
P(f"{'dev_min':>7} {'dev_max':>7} {'van':>4} {'co':>4} {'rep':>4} | {'TRAIN mean/med/win/n':>34} | {'VAL mean/med/win/n':>30}")
for mean, f, s in sel_res[:12]:
    sv = stats(run(VAL, f, BASE_EXIT)) or {"mean":0,"median":0,"win":0,"n":0}
    P(f"{f['dev_min']:>7.1f} {('inf' if f['dev_max']>=1e8 else f['dev_max']):>7} {str(f['vanilla']):>4} "
      f"{str(f['max_cosnipers']):>4} {str(f['max_creator_launches']):>4} | "
      f"{s['mean']:+.4f}/{s['median']:+.4f}/{s['win']*100:3.0f}%/{s['n']:<4} | "
      f"{sv['mean']:+.4f}/{sv['median']:+.4f}/{sv['win']*100:3.0f}%/{sv['n']}")
best_sel = sel_res[0][1] if sel_res else BASE_FILT

# Stage 2: exit params with best selection, on TRAIN
P(f"\nStage 2 — tune exit on TRAIN with best selection {dict((k,v) for k,v in best_sel.items() if k!='rep')}:")
exit_grid = []
for derisk in [0.3, 0.4, 0.5, 0.6, 0.7]:
    for ride in [1.3, 1.6, 2.0]:
        for trail in [0.75, 0.85, 0.9]:
            for cut in [0.8, 0.85, 0.92]:
                for ladder in [0.2, 0.3, 0.4]:
                    for cap in [8, 20, 38]:
                        exit_grid.append({"derisk_frac": derisk, "ride_mult": ride, "trail_frac": trail,
                                          "cut_r": cut, "ladder_frac": ladder, "cap_slots": cap})
ex_res = []
for e in exit_grid:
    p = run(TRAIN, best_sel, e); s = stats(p)
    if s and s["n"] >= 40: ex_res.append((s["mean"], e, s))
ex_res.sort(reverse=True, key=lambda x: x[0])
P(f"  searched {len(exit_grid)} exit configs; top 10 on TRAIN with VAL check:")
P(f"{'derisk':>6} {'ride':>5} {'trail':>5} {'cut':>5} {'lad':>4} {'cap':>4} | {'TRAIN mean/med/win':>26} | {'VAL mean/med/win/n':>28}")
for mean, e, s in ex_res[:10]:
    sv = stats(run(VAL, best_sel, e)) or {"mean":0,"median":0,"win":0,"n":0}
    P(f"{e['derisk_frac']:>6.2f} {e['ride_mult']:>5.1f} {e['trail_frac']:>5.2f} {e['cut_r']:>5.2f} "
      f"{e['ladder_frac']:>4.1f} {e['cap_slots']:>4} | {s['mean']:+.4f}/{s['median']:+.4f}/{s['win']*100:3.0f}% | "
      f"{sv['mean']:+.4f}/{sv['median']:+.4f}/{sv['win']*100:3.0f}%/{sv['n']}")
best_exit = ex_res[0][1] if ex_res else BASE_EXIT

# ---------- C. BEST CONFIG — validated out-of-sample ----------
P("\n## C. BEST train-tuned config, evaluated OUT-OF-SAMPLE on VAL")
P(f"selection: {dict((k,v) for k,v in best_sel.items() if k!='rep')}")
P(f"exit: {best_exit}")
pv = run(VAL, best_sel, best_exit); Sv = stats(pv)
pt = run(TRAIN, best_sel, best_exit); Stn = stats(pt)
P("TRAIN ", line(Stn))
P("VAL   ", line(Sv))
if Sv:
    P(f"  VAL dist R: p10={Sv['p10']:+.3f} p25={Sv['p25']:+.3f} p50={Sv['p50']:+.3f} p75={Sv['p75']:+.3f} p90={Sv['p90']:+.3f} p99={Sv['p99']:+.3f}")
    P(f"  VAL SOL @ {SIZE} SOL: mean={Sv['mean']*SIZE:+.4f}  median={Sv['median']*SIZE:+.4f}")
    srt = sorted(pv, reverse=True)
    if len(srt) > 2:
        no1 = (sum(srt)-srt[0])/(len(srt)-1); no2 = (sum(srt)-srt[0]-srt[1])/(len(srt)-2)
        P(f"  VAL tail check: mean={Sv['mean']:+.4f}  drop top1={no1:+.4f}  drop top2={no2:+.4f}  (top1 R={srt[0]:+.2f} top2 R={srt[1]:+.2f})")

# save
open("/root/profit_backtest/REPORT.md", "w").write("\n".join(out)+"\n")
print("\n[written REPORT.md]")
