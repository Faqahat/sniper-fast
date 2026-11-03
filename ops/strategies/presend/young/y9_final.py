#!/usr/bin/env python3
"""YOUNG step 9: frozen candidates (picked on train) scored on TEST with the corrections:
 raw = simulator; corr = raw - 3.06 mSOL per expected fill (MEASURED age-1 sim optimism, y3: live -8.37 vs sim -5.31 mSOL/fill);
 corr-20 = corr - 20% of each trigger's positive gross (followers haircut). CI90 bootstrap over triggers; w/o top 5; per run; day/night."""
import pickle, collections
from yan import *
import y6_search as S
T = S.T; HTR, HTE = S.HTR, S.HTE
BIAS = 0.00306
C = [  # (name, ages, key, quiet, filter, deployable note)
    ("A0-1 age0 limit 0.70", (0,), ("e70", "base", 0.696), "Q", "any", "yes: limit x0.70 for create-slot triggers"),
    ("A0-2 age0 limit 0.70 + TP 10%", (0,), ("e70", "tp10", 0.696), "Q", "any", "yes"),
    ("A0-3 age0 train #1: limit 0.80, hold +6 slots, whale>=4 SOL", (0,), ("e80", "slow+6", 0.696), "Q", "ws>=4", "yes"),
    ("A1-1 age1 train #1 deployable: no whale-stop, hold +6, day only", (1,), ("e88nowst", "slow+6", 0.696), "Q", "day06-22", "yes"),
    ("A1-2 age1 fill only on the whale's own dump", (1,), ("e88w", "base", 0.696), "Q", "any", "only with an on-chain whale-balance assertion (INFERRED)"),
    ("A1-3 age1 whale's dump + hold +6", (1,), ("e88w", "slow+6", 0.696), "Q", "any", "same"),
    ("REF current recipe age0", (0,), ("e88", "base", 0.696), "Q", "any", "-"),
    ("REF current recipe age1", (1,), ("e88", "base", 0.696), "Q", "any", "-"),
]
def vals(rows, key):
    raw = [r["res"][key]["pnl"] for r in rows]
    corr = [r["res"][key]["pnl"] - BIAS * r["res"][key]["p_fill"] for r in rows]
    c20 = [c - 0.2 * max(r["res"][key]["gross_f"], 0) for c, r in zip(corr, rows)]
    return raw, corr, c20
for name, ages, key, qn, fn, dep in C:
    A = [r for r in T if r["age"] in ages and S.F[fn](r) and (qn == "noQ" or not r["q_all4"])]
    print(f"### {name}  [{key[0]} {key[1]} size {key[2]}, QUIET {qn}, filter {fn}; deployable: {dep}]")
    print("| set | h | exp fills | raw P&L | corr | corr-20% | /day corr @0.696 | CI90 corr | w/o top5 corr | runs help/hurt (corr) |")
    for lab, rows, h in (("train", [r for r in A if not r["test"]], HTR), ("TEST", [r for r in A if r["test"]], HTE)):
        raw, corr, c20 = vals(rows, key); pf = sum(r["res"][key]["p_fill"] for r in rows)
        lo, hi = boot(corr) if corr else (0, 0)
        pr = collections.defaultdict(float)
        for r, c in zip(rows, corr): pr[r["run"]] += c
        print(f"| {lab} | {h:.1f} | {pf:.0f} | {sum(raw):+.3f} | {sum(corr):+.3f} | {sum(c20):+.3f} | {sum(corr)/h*24:+.2f} | [{lo:+.2f}, {hi:+.2f}] | {wo_top(corr):+.3f} | {sum(1 for v in pr.values() if v>0)}/{sum(1 for v in pr.values() if v<0)} |")
    te = [r for r in A if r["test"]]
    for dn, f in (("day 06-22", lambda r: 6 <= r["hour"] < 22), ("night 22-06", lambda r: not (6 <= r["hour"] < 22))):
        rr = [r for r in te if f(r)]; _, corr, _ = vals(rr, key)
        print(f"  TEST {dn}: trig {len(rr)} corr {sum(corr):+.3f}")
    pr = collections.defaultdict(float)
    for r, c in zip(te, vals(te, key)[1]): pr[r["run"]] += c
    print("  TEST per run (corr):", " ".join(f"{k} {v:+.3f}" for k, v in sorted(pr.items())))
    print()
