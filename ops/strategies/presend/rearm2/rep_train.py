#!/usr/bin/env python3
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
import rep
from rep import Day, boot, fmt, NAME, TRAIN, TEST
DAYS = {D: Day(D) for D in (2, 3, 4)}
VARS = [k for k in DAYS[2].out if k != "base"]
S65 = 650_000_000
P = print


def delta_fn(v, size=S65, tp=0.2, cut=0.0, ff=5000, drop_top=0):
    def f(dy, d):
        a = dy.per_hour(v, d, size, tp, cut, ff, drop_top=drop_top); b = dy.per_hour("base", d, size, tp, cut, ff)
        return {h: a.get(h, 0) - b.get(h, 0) for h in set(a) | set(b)}
    return f


def lvl_fn(v, size=S65, tp=0.2, cut=0.0, ff=5000, only=None):
    return lambda dy, d: dy.per_hour(v, d, size, tp, cut, ff, only=only)


# ---------------- TRAIN choice
P("## TRAIN: re-arm minus base, SOL/day, 0.65 SOL TP 20% [90% CI]")
P("| Variant | " + " | ".join(NAME[D] for D in TRAIN) + " | TRAIN pooled | TRAIN pooled, 20% fewer followers |")
P("|---|---|---|---|---|---|")
score = {}
for v in VARS:
    cells = [fmt(*boot([DAYS[D]], delta_fn(v))) for D in TRAIN]
    pooled = boot([DAYS[D] for D in TRAIN], delta_fn(v)); c20 = boot([DAYS[D] for D in TRAIN], delta_fn(v, cut=0.2))
    score[v] = c20[0]
    P(f"| {v} | " + " | ".join(cells) + f" | {fmt(*pooled)} | {fmt(*c20)} |")
best = max(score, key=score.get)
P(f"\nTRAIN-best (by pooled Δ at 20% fewer followers): {best}\n")
pickle.dump(best, open(f"{rep.W}/train_best.pkl", "wb"))
