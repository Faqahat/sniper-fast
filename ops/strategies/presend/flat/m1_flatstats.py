#!/usr/bin/env python3
"""FLAT study (MEASURED): flat-fill share and cost per run; the engine's view at the time exit vs the chain.
usage: m1_flatstats.py r24 r25 r26 r27 [r28]"""
import sys, collections
import numpy as np
import flatlib as FL

def main():
    print(f"{'run':4s} {'size':>5s} {'fills':>5s} {'flat':>4s} {'share':>6s} {'flat net':>9s} {'per flat':>8s} {'%size':>6s} | {'all fills net':>13s} {'non-flat net':>12s} | eng-flat: chain-flat / chain-not | flat exits")
    tot = collections.Counter()
    for run in sys.argv[1:]:
        B = FL.load_base(run); F = [x for x in B["W"] if x["filled"]]
        fl = [x for x in F if x["flat"]]; nf = [x for x in F if not x["flat"]]
        size = sorted(set(x["spend"] for x in F))
        fn = sum(x["net"] for x in fl) / 1e9; an = sum(x["net"] for x in F) / 1e9; nn = sum(x["net"] for x in nf) / 1e9
        pf = fn / max(len(fl), 1)
        pct = np.mean([x["net"] / x["spend"] * 100 for x in fl]) if fl else 0
        ef = [x for x in F if x["eng_flat"]]
        a = sum(1 for x in ef if x["flat"]); b = sum(1 for x in ef if not x["flat"])
        c_ = sum(1 for x in fl if not x["eng_flat"])
        ex = collections.Counter(x["exit"]["why"] for x in fl)
        print(f"{run:4s} {'/'.join(f'{s/1e9:.2f}' for s in size):>5s} {len(F):5d} {len(fl):4d} {len(fl)/len(F)*100:5.1f}% {fn:+9.4f} {pf:+8.4f} {pct:+6.2f} | {an:+13.4f} {nn:+12.4f} | {a} / {b} (chain-flat not eng-flat {c_}) | {dict(ex)}")
        # flat P&L spread
        v = np.array([x["net"] / 1e9 for x in fl])
        if len(v): print(f"      flat net per fill: min {v.min():+.4f} p50 {np.median(v):+.4f} max {v.max():+.4f}; realized only p50 {np.median([x['pnl']/1e9 for x in fl]):+.4f}; rent back p50 {np.median([x['rb']/1e9 for x in fl]):.6f}")
        for k, val in (("fills", len(F)), ("flat", len(fl))): tot[k] += val
main()
