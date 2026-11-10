#!/usr/bin/env python3
"""OBS-STRAT scorer (real money). Input: pos_join-format rows (x2_join.py / h_join for the holdout). Every lever here BLOCKS live
trades (or cuts their window), so its value = minus the realized P&L of the trades it removes (exact, PROOF rule 3).
Baseline = what ran, plus dip32's cr_loss 2:0.05 creator gate replayed in time order (kept positions only, known at last sell
landing + 2 s, ledger empty at the first file) so every lever is scored ON TOP of dip32.
Levers (all existing engine flags, decided before the order can fill):
  R5   : re-arm window skipped when all four QUIET arm signals hold for its largest holder (obs rearm_window.r5_skip, the shadow
         of psrearm.rs R5)                                -> --presend-live-rearm-r5-skip on
  GAPg : re-arm window's last slot = dump + 3 + g (fills later than that are removed)  -> --presend-live-rearm-gap-slots g
  W<n> : T2 window cut after n slots (fills with slots_after_trigger > n removed)     -> --presend-window-slots n
usage: s1_score.py ROWS.jsonl [--hours DEV=74.35,VAL=20.61] [--grid] [--json OUT]"""
import sys, json, collections, argparse
ap = argparse.ArgumentParser(); ap.add_argument("rows"); ap.add_argument("--hours", default="DEV=74.35,VAL=20.61")
ap.add_argument("--grid", action="store_true"); ap.add_argument("--json"); ap.add_argument("--no-crloss", action="store_true"); ap.add_argument("--write-kept", help="rows kept by cr_loss + R5 (for the combined exit score)")
A = ap.parse_args()
HRS = {k: float(v) for k, v in (x.split("=") for x in A.hours.split(","))}
rows = sorted((json.loads(l) for l in open(A.rows)), key=lambda d: d["t"])

# ---- dip32 cr_loss 2:0.05 (kept positions only) ----
def creator(d):
    return (d.get("ann_creator") or ((d.get("arm_ann") or {}).get("creator")))
led = collections.defaultdict(list)
for d in rows:
    c = creator(d); d["crb"] = False
    if c and not A.no_crloss:
        prev = [q for q in led[c] if q[0] < d["t0"]]
        if len(prev) >= 2 and sum(q[1] for q in prev) <= -0.05: d["crb"] = True
    if c and not d["crb"]: led[c].append((d["known"], d["pnl"]))
base = [d for d in rows if not d["crb"]]

def R5(d): return d["kind"] == "rearm" and bool((d.get("rw") or {}).get("r5_skip"))
def GAP(g): return lambda d: d["kind"] == "rearm" and d["fslot"] - d["dump"]["slot"] > 3 + g
def W(n): return lambda d: d["kind"] == "t2" and (d.get("sat") or 0) > n
LEV = {"R5": R5, "GAP10": GAP(10), "W7": W(7)}
LEV["R5+GAP10"] = lambda d: R5(d) or GAP(10)(d)
LEV["R5+GAP10+W7"] = lambda d: R5(d) or GAP(10)(d) or W(7)(d)
if A.grid:
    for g in (4, 6, 8, 10, 12, 14, 16): LEV[f"GAP{g}"] = GAP(g)
    for n in (4, 5, 6, 7, 8, 9): LEV[f"W{n}"] = W(n)

def stats(ds, f):
    blk = [d for d in ds if f(d)]
    saved = -sum(d["pnl"] for d in blk)
    big = sorted((-d["pnl"] for d in blk), reverse=True)
    allp = sorted((d["pnl"] for d in ds), reverse=True); top5 = set(id(d) for d in sorted(ds, key=lambda d: -d["pnl"])[:5])
    after = [d for d in ds if not f(d)]
    return dict(n=len(ds), blocked=len(blk), winners_lost=sum(1 for d in blk if d["pnl"] > 0), win_sol_lost=round(sum(d["pnl"] for d in blk if d["pnl"] > 0), 3),
                saved=round(saved, 3), saved_wo_its5best=round(sum(big[5:]), 3),
                saved_wo_top5_trades=round(-sum(d["pnl"] for d in blk if id(d) not in top5), 3),
                base=round(sum(d["pnl"] for d in ds), 3), base_win=round(sum(d["pnl"] > 0 for d in ds) / max(len(ds), 1), 3),
                after=round(sum(d["pnl"] for d in after), 3), after_win=round(sum(d["pnl"] > 0 for d in after) / max(len(after), 1), 3))
out = {"crloss_blocked": {p: sum(1 for d in rows if d["crb"] and d["per"] == p) for p in HRS}, "levers": {}}
pers = list(HRS)
print("baseline (ran + dip32 cr_loss replay):", {p: (sum(1 for d in base if d['per'] == p), round(sum(d['pnl'] for d in base if d['per'] == p), 3)) for p in pers},
      "| cr_loss blocked", out["crloss_blocked"])
print(f"{'lever':12s} " + " | ".join(f"{p+' blk(win)':>14s} {'saved':>7s} {'/day':>6s} {'w/o5best':>8s} {'win%':>9s}" for p in pers))
for name, f in LEV.items():
    o = out["levers"][name] = {}
    s = []
    for p in pers:
        ds = [d for d in base if d["per"] == p]; st = stats(ds, f); st["per_day"] = round(st["saved"] / HRS[p] * 24, 2); o[p] = st
        runs = collections.OrderedDict()
        for d in ds: runs.setdefault(d["run"], []).append(d)
        st["per_run"] = {r: stats(v, f)["saved"] for r, v in runs.items()}
        s.append(f"{st['blocked']:7d}({st['winners_lost']:4d}) {st['saved']:+7.3f} {st['per_day']:+6.2f} {st['saved_wo_its5best']:+8.3f} {100*st['base_win']:4.1f}>{100*st['after_win']:4.1f}")
    print(f"{name:12s} " + " | ".join(s))
for name in ("R5", "GAP10", "W7", "R5+GAP10"):
    print(name, "per run:", {p: out["levers"][name][p]["per_run"] for p in pers})
if A.json: json.dump(out, open(A.json, "w"), indent=1)
if A.write_kept:
    with open(A.write_kept, "w") as o:
        for d in base:
            if not R5(d): o.write(json.dumps(d) + "\n")
