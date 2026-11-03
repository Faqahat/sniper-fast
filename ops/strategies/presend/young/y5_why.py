#!/usr/bin/env python3
"""YOUNG step 5: why age 0 / 1 lose (current recipe e88/base at 0.696 SOL), split by who dumps, dev vs whale, curve stage."""
import pickle, collections, statistics as st
from yan import *
T = pickle.load(open(f"{D}/table_0_1.pkl", "rb"))
T2 = pickle.load(open(f"{D}/table_99.pkl", "rb")) if __import__("os").path.exists(f"{D}/table_99.pkl") else []
K = ("e88", "base", 0.696)
def summ(rows, key=K, lab=""):
    pf = sum(r["res"][key]["p_fill"] for r in rows); pn = sum(r["res"][key]["pnl"] for r in rows)
    gf = sum(r["res"][key]["gross_f"] for r in rows)
    print(f"{lab:38s} trig {len(rows):5d} exp fills {pf:6.1f} P&L {pn:+7.3f} SOL  per fill {1e3*pn/max(pf,1e-9):+6.2f} mSOL  gross/fill {1e3*gf/max(pf,1e-9):+6.2f}")
for age in (0, 1):
    A = [r for r in T if r["age"] == age]
    print(f"== age {age}")
    summ(A, lab="all")
    summ([r for r in A if not r["q_all4"]], lab="QUIET would arm (not all4)")
    summ([r for r in A if r["q_all4"]], lab="QUIET would skip (all4)")
    summ([r for r in A if not r["test"]], lab="train"); summ([r for r in A if r["test"]], lab="test")
    summ([r for r in A if r["whale_is_dev"]], lab="whale = dev (first buyer)")
    summ([r for r in A if not r["whale_is_dev"]], lab="whale != dev")
    for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 99)):
        summ([r for r in A if lo <= r["whale_sol"] < hi], lab=f"whale sol {lo}-{hi}")
    for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 999)):
        summ([r for r in A if lo <= r["n_pre_buyers"] < hi], lab=f"buyers before trig {lo}-{hi}")
    # among fills: dumper whale vs not, sells in hold
    w = sum(r["res"][K]["dump_is_whale"] for r in A); pf = sum(r["res"][K]["p_fill"] for r in A)
    print(f"  fills where the dump is the whale's own sell: {w/pf:.0%}; mean sells during hold {sum(r['res'][K]['nsell_hold'] for r in A)/pf:.2f}, sol sold in hold {sum(r['res'][K]['sell_sol_hold'] for r in A)/pf:.3f} SOL/fill, drop at dump {sum(r['res'][K]['drop'] for r in A)/pf:.1%}, fill slot after trig {sum(r['res'][K]['d_slot'] for r in A)/pf:.1f}")
if T2:
    print("== age >= 2 (reference)"); summ(T2, lab="all"); summ([r for r in T2 if not r["q_all4"]], lab="QUIET arm")
    pf = sum(r["res"][K]["p_fill"] for r in T2); w = sum(r["res"][K]["dump_is_whale"] for r in T2)
    print(f"  dump=whale {w/pf:.0%}; sells in hold {sum(r['res'][K]['nsell_hold'] for r in T2)/pf:.2f}, sol sold in hold {sum(r['res'][K]['sell_sol_hold'] for r in T2)/pf:.3f}, drop {sum(r['res'][K]['drop'] for r in T2)/pf:.1%}")
