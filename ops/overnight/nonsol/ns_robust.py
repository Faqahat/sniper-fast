#!/usr/bin/env python3
# Robustness of the only positive cell family (logistic top-2% picks, OUT-OF-SAMPLE test sets of both directions):
# per landing / exit / variant: total, fills, median, win rate, total without the best 5, halves; cost sensitivity
# (buy overhead 2% vs 0.6% "pro cost"; swap leg per side 0 / 0.1 / 0.3 / 0.6 / 1.0 / 1.5%). -> robust.txt
import sys, os, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
from ns_lib import *
rows = {r["m"]: r for r in load_rows()}
RES = json.load(open(os.path.join(DATA, "select_res.json")))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1])
for cut in ("0.02", "0.05"):
    for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
        sel = [rows[m] for m in RES[f"logit_{tr_run}_top{cut}"]["test"]]
        P(f"\n=== model trained on {tr_run}, top {float(cut):.0%} -> TEST {te_run}: {len(sel)} picks")
        for Lm in (30, 45, 75):
            for var in ("base", "strict", "harsh"):
                for ex in ("2.0", "3.0", "5.0", "8.0", "10.0"):
                    d = summ(sel, Lm, var, ex); h1, h2 = halves(sel, Lm, var, ex)
                    if ex in ("5.0", "8.0", "10.0") or var == "strict":
                        P(f"   L{Lm} {var:6s} t{ex[:-2]:2s} {fmt(d)} | halves {h1:+.2f} / {h2:+.2f}")
        P("   cost sensitivity, strict, t5 / t8 (total SOL):")
        for oh in (0.02, 0.006):
            for s in (0.0, 0.001, 0.003, 0.006, 0.01, 0.015):
                P(f"      overhead {oh:.1%} swap leg {s:.1%}: " + " | ".join(f"L{Lm} t5 {summ(sel,Lm,'strict','5.0',oh,s)['tot']:+6.2f} t8 {summ(sel,Lm,'strict','8.0',oh,s)['tot']:+6.2f}" for Lm in (30, 45, 75)))
open(os.path.join(HERE, "robust.txt"), "w").write("\n".join(out) + "\n")
