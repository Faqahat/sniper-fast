#!/usr/bin/env python3
"""FLAT study: baseline check (as run vs QUIET replayed) per run; must reproduce the earlier studies' numbers.
usage: m2_baseline.py r24 r25 r26 r27"""
import sys
import flatlib as FL, evalcore as EC

def main():
    runs = sys.argv[1:]
    phases = sorted(set(p for r in runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); O = EC.Others(C)
    for run in runs:
        B = FL.load_base(run)
        _, A = EC.evaluate(B["W"], O, run, mode="asrun")
        _, P = EC.evaluate(B["W"], O, run, mode="asrun", extra_skip=(lambda w: bool(w.get("quiet_skip_replay"))) if run in EC.DEV else None,
                           extra_stops=[(6, 2)] if run in EC.DEV else [])
        print(f"{run}: as run {A['base']:+.4f} (fills {A['fills']}, fees {sum(w['fail_fee'] for w in B['W'])/1e9:.4f}) | with QUIET replayed {P['var']:+.4f} "
              f"(gain {P['gain']:+.4f}; winners removed {P['win_rm']} {P['win_rm_sol']:+.4f}, losers removed {P['lose_rm']} {P['lose_rm_sol']:+.4f}, flats removed {P['flat_rm']})")
main()
