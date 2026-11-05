#!/usr/bin/env python3
"""SMARTEXIT step 9 (POST-FREEZE DIAGNOSTIC, not a test): why the DEV leaders failed.  Exact-timer curve per split and per run
group; the clock's two arms separately.  Nothing here is eligible as a pass (VAL/HOLD already seen)."""
import sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L, spol as P
ALL, J, _ = L.load_fills()
grp = {"dev": lambda f: f.split == "dev", "val": lambda f: f.split == "val", "hold r43-50": lambda f: f.split == "hold" and f.run <= 50,
       "hold r51-55": lambda f: f.run >= 51}
HS = (50, 75, 100, 110, 125, 140, 160, 200, 300, 600, 1000, 2000)
for g, sel in grp.items():
    F = [f for f in ALL if sel(f)]
    E0 = [L.events(f) for f in F]; E2 = [L.events(f, 0.2) for f in F]
    b0 = sum(P.run_policy(f, e, P.p_timer(125)) for f, e in zip(F, E0)); b2 = sum(P.run_policy(f, e, P.p_timer(125), 0.2) for f, e in zip(F, E2))
    row = []; row2 = []
    for H in HS:
        row.append(sum(P.run_policy(f, e, P.p_timer(H)) for f, e in zip(F, E0)) - b0)
        row2.append(sum(P.run_policy(f, e, P.p_timer(H), 0.2) for f, e in zip(F, E2)) - b2)
    print(f"{g:12} n {len(F):4} t125 {b0:+7.3f} | " + " ".join(f"t{H}:{v:+.2f}" for H, v in zip(HS, row)))
    print(f"{'  fc20':12} {'':6} t125 {b2:+7.3f} | " + " ".join(f"t{H}:{v:+.2f}" for H, v in zip(HS, row2)))
    # clock arms
    risky = [(f, e) for f, e in zip(F, E0) if P.clock_risk(f, 1.0, 0)]; safe = [(f, e) for f, e in zip(F, E0) if not P.clock_risk(f, 1.0, 0)]
    for nm, S in (("risky", risky), ("safe", safe)):
        bb = sum(P.run_policy(f, e, P.p_timer(125)) for f, e in S)
        print(f"    clock {nm:5} n {len(S):4} t125 {bb:+.3f} | " + " ".join(f"t{H}:{sum(P.run_policy(f, e, P.p_timer(H)) for f, e in S) - bb:+.2f}" for H in (75, 100, 160, 200)))
