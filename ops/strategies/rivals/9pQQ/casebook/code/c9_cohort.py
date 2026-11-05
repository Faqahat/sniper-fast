#!/usr/bin/env python3
"""per trip: buy-trigger cohort (outside BUYERS in [buy-3 slots, buy]) and when they sell vs 9pQQ's sell. usage: RUN MINT"""
import sys, json, gzip
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
run, mint = sys.argv[1], sys.argv[2]
R = [json.loads(l) for l in gzip.open(f"{D}/tapes/{run}/{mint}.ev.jsonl.gz", "rt")]
own = [k for k, r in enumerate(R) if r["own"]]
for a, b in zip(own[::2], own[1::2]):
    B, S = R[a], R[b]
    coh = {r["u"] for r in R[max(0, a - 30):a] if not r["own"] and r["buy"] and r["s"] >= B["s"] - 3}
    cohS = {r["u"] for r in R[max(0, a - 30):a] if not r["own"] and not r["buy"] and r["s"] >= B["s"] - 3}
    fs = next((r for r in R[a + 1:] if r["u"] in coh and not r["buy"]), None)
    lastbuyers = {r["u"] for r in R[a + 1:b] if not r["own"] and r["buy"]}
    pre = [r for r in R[max(0, b - 4):b] if not r["own"]]
    print(f"buy +{B['age']} sell +{S['age']} hold {S['s']-B['s']:5d} | cohortB {len(coh)} first cohort sell at {('+'+str(fs['age'])+' d'+str(fs['s']-S['s'])) if fs else 'none'}"
          f" | pre-sell: " + " ".join(f"{'B' if r['buy'] else 'S'}{r['sol']:.2f}{'*C' if r['u'] in coh else ''}{'*F' if r['u'] in lastbuyers else ''}" for r in pre))
