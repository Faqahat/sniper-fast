#!/usr/bin/env python3
"""LIM step 12 (read-only): population view of haqq's limits, per day. Size classes from the tape fills (spend net of the 1.25% fee)
mapped to the limit rule seen in the RPC sample (l6/l6b): 0.01/0.1/0.15/0.25/0.3/0.35/0.4 -> no limit (min_out 1);
0.275 -> wide limit; 0.5 -> 8% vs the latest sell's post-state; 0.75/0.7875/1.0/1.25 -> 2% vs the latest sell's post-state.
Every failed buy is a limited buy (6042 = min_out not met; 99.8% of his fails). Binding rate = fails / (limited fills + fails).
DIP = first buy within 2 slots of a >=5% sell (l5). Also: P&L of DIP lots by later-add (self-support) split.
Out: data/lim/l12.txt"""
import pickle, sys, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
def cls(sp):
    x = sp / 1.0125
    if x < 0.2: return "tiny<0.2 (none)"
    if 0.26 < x < 0.28: return "0.275 (wide)"
    if x < 0.45: return "0.25-0.4 (none)"
    if x < 0.6: return "0.5 (8%)"
    return "0.75-1.25 (2%)"
H = pickle.load(open(f"{OUT}/hctx2.pkl", "rb"))
days = sorted({r["day"] for r in H})
P("# haqq limits, population (tape fills by size class + all failed buys), per day - MEASURED (rule per class from the RPC sample)")
for nm, sel in (("ALL buys", lambda r: True), ("DIP buys", lambda r: r["dip"])):
    P(f"\n## {nm}")
    P("| day | fills none-limit | fills limited | fails (all 6042-type) | share of buy txs with NO limit | binding rate of limited buys |"); P("|---|---|---|---|---|---|")
    for d in days + ["all"]:
        v = [r for r in H if sel(r) and (d == "all" or r["day"] == d)]
        fn = sum(1 for r in v if r["ok"] and "spend" in r and "none" in cls(r["spend"])); fl = sum(1 for r in v if r["ok"] and "spend" in r and "none" not in cls(r["spend"]))
        fx = sum(1 for r in v if not r["ok"])
        P(f"| {d if d == 'all' else L.day_name(d)} | {fn} | {fl} | {fx} | {100*fn/max(fn+fl+fx,1):.0f}% | {100*fx/max(fl+fx,1):.0f}% |")
F = [r for r in H if r["dip"] and r["ok"] and "spend" in r and "lot_pnl" in r]
P("\n## DIP fills by size class: lots, mSOL/lot, %/SOL (before tx costs), pr p50/p90, buys ahead p50")
for c in sorted({cls(r["spend"]) for r in F}):
    v = [r for r in F if cls(r["spend"]) == c]
    p = np.array([r["lot_pnl"] for r in v])
    P(f"- {c}: {len(v)} lots, {p.sum():+.2f} SOL, {1000*p.mean():+.2f} mSOL/lot, {100*p.sum()/sum(r['lot_cost'] for r in v):+.2f}%/SOL, pr {np.median([r['pr'] for r in v]):.3f}/{np.percentile([r['pr'] for r in v],90):.3f}, buys ahead p50 {np.median([r['nb_ahead'] for r in v]):.0f}")
lim = pickle.load(open(f"{OUT}/limits_ref.pkl", "rb"))
fl = [r for r in lim if r["ok"] and r.get("tol_pos") is not None]
if fl: P(f"\nroom left on FILLED limited buys in the RPC sample (tokens got / min_out - 1): n {len(fl)}, p10/50/90 " + " / ".join(f"{100*x:+.1f}%" for x in np.percentile([r['tol_pos'] for r in fl], [10, 50, 90])))
open(f"{OUT}/l12.txt", "w").write("\n".join(out) + "\n")
