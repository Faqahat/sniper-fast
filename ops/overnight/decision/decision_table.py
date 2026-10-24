#!/usr/bin/env python3
# Decision table for the owner: FINAL-2 out of sample, by landing time and cost model, all clean windows.
# Windows: R2 overnight live picks (core/final2_picks_v3_become_B0.5_vfix4.json), R1 clean daytime tail (lab_cF2_R1_..._vfix4.json).
# Cost models (0.5 SOL): today = 2% overhead per landed buy, 0.005 per failed buy (the replay's own numbers)
#   CW-style = 1.2% (0.003 priority + 0.003 tip), 0.003 per failed | Run 2 real = 4.7% (0.0235), 0.0105 per failed.
import json, random, statistics
CORE = "/home/moiz/sniper/ops/overnight/core"
WIN = {"R2 overnight 8.3 h": f"{CORE}/final2_picks_v3_become_B0.5_vfix4.json", "R1 daytime tail 3 h": f"{CORE}/lab_cF2_R1_become_B0.5_vfix4.json"}
COST = {"today": (0.0, 0.005), "CW-style": (+0.004, 0.003), "Run 2 fees": (-0.0135, 0.0105)}
def vals(R, Lm, var, ex, cm):
    adj, fail = COST[cm]; out = []
    for r in R:
        x = r[Lm][var]
        if x is None: continue
        out.append(x["pnl"][ex] + adj if x["fill"] else -fail)
    return out
def boot(v, n=2000):
    rnd = random.Random(7); k = len(v)
    return sum(1 for _ in range(n) if sum(v[rnd.randrange(k)] for _ in range(k)) > 0) / n
rows = []
for wn, f in WIN.items():
    R = json.load(open(f))
    for Lm in ("30", "45", "60", "75"):
        for var in ("slip", "proafter_slip", "nosnip"):
            for cm in COST:
                v = vals(R, Lm, var, "t8", cm); fills = sum(1 for r in R if r[Lm][var] and r[Lm][var]["fill"])
                srt = sorted(v)
                rows.append(dict(w=wn, L=Lm, var=var, cost=cm, n=len(v), fills=fills, tot=round(sum(v), 2), wo5=round(sum(srt[:-5]), 2), p=round(boot(v), 2)))
json.dump(rows, open("/home/moiz/sniper/ops/overnight/decision/decision_table.json", "w"))
print("FINAL-2, 0.5 SOL, sell at 8 s. Total SOL (fills) [without best 5] {bootstrap P(total>0)}")
for var in ("proafter_slip", "slip", "nosnip"):
    print(f"\n== variant {var}")
    for cm in COST:
        print(f"  cost {cm}:")
        for Lm in ("30", "45", "60", "75"):
            cells = []
            for wn in WIN:
                r = next(x for x in rows if x["w"] == wn and x["L"] == Lm and x["var"] == var and x["cost"] == cm)
                cells.append(f"{wn}: {r['tot']:+6.2f} ({r['fills']:3d}) [{r['wo5']:+6.2f}] {{{r['p']:.2f}}}")
            comb = [x for x in rows if x["L"] == Lm and x["var"] == var and x["cost"] == cm]
            print(f"    {Lm} ms | " + " | ".join(cells) + f" | both {sum(x['tot'] for x in comb):+6.2f}")
