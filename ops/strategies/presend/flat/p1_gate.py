#!/usr/bin/env python3
"""FLAT study, POST-HOC (written after the holdout test; NOT pre-registered, exploratory only): a try-time GATE instead of a stop:
a try is sent only when the engine had seen >= M other trades (not the whale, not us) since the trigger when signing it (its pos);
the window stays armed, so later tries go out once M is reached. A fill whose try is gated is removed; the window is then charged
the tries it would have sent to its end at the run's mean failed fee (as filter/sim.py; conservative: no later fill assumed).
On top of the primary baseline (dev: QUIET replayed). usage: p1_gate.py r24 r25 r26 r27 r28"""
import sys, collections
import numpy as np
import flatlib as FL, evalcore as EC

def main():
    runs = sys.argv[1:]
    phases = sorted(set(p for r in runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); O = EC.Others(C)
    for M in (1, 2):
        print(f"== gate M={M}")
        for run in runs:
            W = FL.load_base(run)["W"]
            bskip, bstops = EC.base_cfg(run, "primary")
            rate = sum(w["fail_fee"] for w in W) / max(sum(len(w["tries"]) for w in W), 1)
            S = collections.Counter()
            for w in W:
                b = EC.run_rules(w, O, skip=bskip(w), stops=bstops)
                if b["skipped"]: continue
                fees = 0; fill_kept = w["filled"]
                for k, t in enumerate(w["tries"]):
                    if b["stop_k"] is not None and k >= b["stop_k"]: break
                    ok = O.upto(w, t["pos"]) >= M
                    if ok: fees += t["fee"]
                    if t["fill"]: fill_kept = ok
                if w["filled"] and b["fill_kept"] and not fill_kept:
                    fees += max(w["en_slot"] - w["fill"]["slot"], 0) * w["k"] * rate
                v = ((w["net"] if (w["filled"] and fill_kept and b["fill_kept"]) else 0) - fees)
                S["base"] += b["score"] / 1e9; S["var"] += v / 1e9
                if w["filled"] and b["fill_kept"] and not fill_kept:
                    if w["net"] > 0: S["win_rm"] += 1; S["win_sol"] += w["net"] / 1e9
                    else: S["lose_rm"] += 1; S["lose_sol"] += w["net"] / 1e9
                    if w["flat"]: S["flat_rm"] += 1
            print(f"  {run}: {S['base']:+.4f} -> {S['var']:+.4f} (gain {S['var'] - S['base']:+.4f}) | winners removed {S['win_rm']} ({S['win_sol']:+.4f}), losers removed {S['lose_rm']} ({S['lose_sol']:+.4f}), flats removed {S['flat_rm']}")
main()
