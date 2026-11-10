#!/usr/bin/env python3
"""EXITPICK step 6: decision-model comparison (own delay / resampled / clock / token-event) and the silent-token rules."""
import json, collections
from elib import *
R = load(); A = json.load(open(f"{O}/alt.json"))
for r in R: r["alt"] = A[r["sig"]]
def S(rows, f): 
    v = [f(r) for r in rows]; return sum(a for a in v if a is not None), sum(1 for a in v if a is None)
groups = [("dev", lambda r: r["split"] == "dev"), ("val", lambda r: r["split"] == "val"), ("hold", lambda r: r["split"] == "hold"), ("ALL", lambda r: True)]
print("DECISION MODEL x TIMER (SOL; own = exit125's own delay; rs = resampled delay; clock = exact timer; tokev = token's next trade)")
for name, c in groups:
    rows = [r for r in R if c(r)]
    print(f" {name} n{len(rows)}")
    for X_ in (100, 125, 150, 200, 400, 1000):
        k = f"t{X_}"
        print(f"   {X_:>5} ms: own {S(rows, lambda r: r['y'][k])[0]:+7.3f} | rs {S(rows, lambda r: r['y_rs'][k])[0]:+7.3f} | clock {S(rows, lambda r: r['alt'][f'clock{X_}'])[0]:+7.3f} | tokev {S(rows, lambda r: r['alt'][f'tokev{X_}'])[0]:+7.3f}"
              f"  || fc20: own {S(rows, lambda r: r['y_fc'][k])[0]:+7.3f} clock {S(rows, lambda r: r['alt'][f'clock{X_}_fc'])[0]:+7.3f} tokev {S(rows, lambda r: r['alt'][f'tokev{X_}_fc'])[0]:+7.3f}")
print("\nSILENT TOKEN (no trade on it seen between our fill and 125 ms - D):")
for D in (0, 15, 30):
    for name, c in groups:
        rows = [r for r in R if c(r)]; sil = [r for r in rows if r["alt"][f"silent{D}"]]
        base_own = sum(r["y"]["t125"] for r in sil); base_clk = sum(r["alt"]["clock125"] for r in sil)
        nxt = [r["alt"][f"next_{D}"] for r in sil]
        nb = sum(1 for a in nxt if a and a["buy"]); ns = sum(1 for a in nxt if a and not a["buy"]); nn = sum(1 for a in nxt if not a)
        line = f"  D{D:>2} {name:>4}: silent {len(sil):>4}/{len(rows):<4} next trade buy {nb} sell {ns} none {nn} | on silent: t125 own {base_own:+.3f} clock {base_clk:+.3f} t1000 own {sum(r['y']['t1000'] for r in sil):+.3f}"
        for rule in ("r3a", "r3b", "r3d"):
            v = [r["alt"][f"{rule}_{D}"] for r in sil]; vf = [r["alt"][f"{rule}_{D}_fc"] for r in sil]
            g = sum(a for a in v if a is not None); miss = sum(1 for a in v if a is None)
            gf = sum(a for a in vf if a is not None)
            line += f" | {rule} {g:+.3f} (vs own {g - base_own:+.3f}, vs clock {g - base_clk:+.3f}; fc20 vs clock {gf - sum(r['alt']['clock125_fc'] for r in sil):+.3f}){' miss ' + str(miss) if miss else ''}"
        print(line)
# per-run for D15, R3a/R3b vs clock125
print("\nPER RUN (D15), gain of rule over clock t125 on silent fills:")
for run in range(42, 51):
    sil = [r for r in R if r["run"] == run and r["alt"]["silent15"]]
    if not sil: continue
    b = sum(r["alt"]["clock125"] for r in sil)
    print(f"  r{run}: silent {len(sil)} | r3a {sum(r['alt']['r3a_15'] or 0 for r in sil) - b:+.3f} | r3b {sum(r['alt']['r3b_15'] or 0 for r in sil) - b:+.3f} | r3d {sum(r['alt']['r3d_15'] or 0 for r in sil) - b:+.3f} | t1000-own vs own125 {sum(r['y']['t1000'] - r['y']['t125'] for r in sil):+.3f}")
