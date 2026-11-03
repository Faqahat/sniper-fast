#!/usr/bin/env python3
"""YOUNG step 6: recipe search on TRAIN (runs before 10-28 00:00 PKT) only; every recipe = entry x exit x size x
(QUIET on/off) x (one arm-time filter). Picks are then scored FROZEN on TEST (10-28 00:00 PKT on). Expected-value P&L
(ysim.esim) per unique trigger; train/test hours = union of run spans."""
import pickle, collections, sys
from yan import *
T = pickle.load(open(f"{D}/table_0_1.pkl", "rb"))
HTR, HTE = hours(False), hours(True)
F = {
    "any": lambda r: True,
    "ws<2": lambda r: r["whale_sol"] < 2, "ws2-4": lambda r: 2 <= r["whale_sol"] < 4, "ws>=4": lambda r: r["whale_sol"] >= 4,
    "ws<3": lambda r: r["whale_sol"] < 3, "ws>=3": lambda r: r["whale_sol"] >= 3, "ws>=6": lambda r: r["whale_sol"] >= 6,
    "pct<10": lambda r: r["pct"] < 10, "pct>=10": lambda r: r["pct"] >= 10, "pct>=15": lambda r: r["pct"] >= 15,
    "pre_buyers<=2": lambda r: r["n_pre_buyers"] <= 2, "pre_buyers>=3": lambda r: r["n_pre_buyers"] >= 3,
    "cs_buyers<=1": lambda r: r["n_cs_buyers"] <= 1, "cs_buyers>=2": lambda r: r["n_cs_buyers"] >= 2,
    "after0": lambda r: r["post_trig_buys_same_slot"] == 0, "after>=1": lambda r: r["post_trig_buys_same_slot"] >= 1,
    "after>=3": lambda r: r["post_trig_buys_same_slot"] >= 3,
    "night22-06": lambda r: r["hour"] >= 22 or r["hour"] < 6, "day06-22": lambda r: 6 <= r["hour"] < 22,
    "devsol<1": lambda r: (r["dev_sol"] or 0) < 1, "devsol>=1": lambda r: (r["dev_sol"] or 0) >= 1, "devsol>=3": lambda r: (r["dev_sol"] or 0) >= 3,
    "vsol<40": lambda r: r["vsol_trig"] < 40, "vsol>=40": lambda r: r["vsol_trig"] >= 40, "vsol>=50": lambda r: r["vsol_trig"] >= 50,
    "wprev0": lambda r: r["whale_prev_buys"] == 0, "wprev>=1": lambda r: r["whale_prev_buys"] >= 1,
}


def score(rows, key):
    v = [r["res"][key]["pnl"] for r in rows]; pf = sum(r["res"][key]["p_fill"] for r in rows)
    return sum(v), pf, v


def main(age_set, lab):
    A = [r for r in T if r["age"] in age_set]
    TR = [r for r in A if not r["test"]]; TE = [r for r in A if r["test"]]
    keys = sorted(A[0]["res"].keys(), key=str)
    out = []
    for key in keys:
        for qn in ("Q", "noQ"):
            for fn, f in F.items():
                rtr = [r for r in TR if f(r) and (qn == "noQ" or not r["q_all4"])]
                s, pf, v = score(rtr, key)
                if pf < 25: continue
                out.append((s, key, qn, fn, pf, wo_top(v)))
    out.sort(key=lambda x: -x[0])
    print(f"===== {lab}: train {HTR:.1f} h, test {HTE:.1f} h; {len(out)} recipes with >= 25 exp train fills; positive on train: {sum(1 for o in out if o[0] > 0)}")
    print("rank | entry exit size | QUIET | filter | TRAIN exp fills, P&L, /day, w/o top5 | TEST exp fills, P&L, /day, CI90, w/o top5")
    for i, (s, key, qn, fn, pf, wt) in enumerate(out[:15]):
        rte = [r for r in TE if F[fn](r) and (qn == "noQ" or not r["q_all4"])]
        s2, pf2, v2 = score(rte, key); lo, hi = boot(v2) if v2 else (0, 0)
        print(f"{i+1:2d} | {key[0]} {key[1]} {key[2]} | {qn} | {fn} | {pf:.0f} {s:+.3f} {s/HTR*24:+.2f}/d w/o5 {wt:+.3f} | {pf2:.0f} {s2:+.3f} {s2/HTE*24:+.2f}/d [{lo:+.2f},{hi:+.2f}] w/o5 {wo_top(v2):+.3f}")
    return out


if __name__ == "__main__":
    for ages, lab in (((0,), "AGE 0"), ((1,), "AGE 1"), ((0, 1), "AGE 0+1")):
        main(set(ages), lab)
