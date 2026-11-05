#!/usr/bin/env python3
"""BIGLOSS b5: DEV-ONLY grid of rule families. Prints DEV metrics only (VAL/HOLD are not computed here)."""
import sys, itertools
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/bigloss")
from bscore import *
from brules import *
R_all = load_feats()
R = [r for r in R_all if r["set"] == "DEV"]
H, HR = hours()
rows = []
def run(name, rl):
    o = report(simulate(R, *rl), sets=("DEV",), H=H)
    rows.append((name, o)); return o
run("creator ledger 2:-0.05 (reference)", make_creator())
for k, X, pmin, tau, kinds in itertools.product((1, 2, 3, 4), (0.0, -0.03, -0.06, -0.1, -0.2), (2.0, 4.0), (None, 6, 24),
                                                (("t2", "rearm"), ("t2",), ("rearm",))):
    run(f"DUMPER k{k} X{X} p{pmin} tau{tau} {'+'.join(kinds)}", make_dumper(k, X, pmin, tau_h=tau, kinds=kinds))
for k, X, pmin, tau, mr in itertools.product((2, 3, 5, 8), (0.0, -0.05, -0.1, -0.2), (2.0, 4.0), (None, 12), (0.0, 0.3)):
    run(f"PRESENCE k{k} X{X} p{pmin} tau{tau} rate{mr}", make_presence(k, X, pmin, tau_h=tau, min_rate=mr))
for k, X, tau, nr in itertools.product((1, 2, 3, 5), (0.0, -0.05, -0.1, -0.2), (None, 12), (1, 2)):
    run(f"WHALE k{k} X{X} tau{tau} resold>={nr}", make_whale(k, X, tau_h=tau, need_resold=nr))
rows.sort(key=lambda x: -x[1]["DEV"]["saved"])
for name, o in rows[:60]: print(fmt(name, o), o["DEV"]["per_run"])
print("...worst 5")
for name, o in rows[-5:]: print(fmt(name, o))
