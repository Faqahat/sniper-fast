#!/usr/bin/env python3
# OUT-OF-SAMPLE check of the replayed families: every filter combination x exit is scored on R2 (day 1); the best R2 rules
# (min events) are then reported on R3 (day 2) unchanged. Our costs are already in the replay P&L (s7_replay.py).
# -> /home/moiz/sniper-data/strategies/replay_select.json + printed table
import json, gzip, glob, itertools, collections
import numpy as np
OUT = "/home/moiz/sniper-data/strategies"
rows = []
for f in sorted(glob.glob(f"{OUT}/replay/*.jsonl.gz")):
    for l in gzip.open(f, "rt"): rows.append(json.loads(l))
print("rows", len(rows))
fam = json.load(open(f"{OUT}/families.json"))["fam_of"]
F7W = {u[:8] for u, f in fam.items() if f == "F7"}
res = {}
def evaluate(kind, lat, feats, grid, minN, size_key=None):
    R = [r for r in rows if r["kind"] == kind and r["lat"] == lat]
    if not R: return None
    exits = list(next(r for r in R if r.get("pnl"))["pnl"])
    run = np.array([r["run"] for r in R])
    P = np.array([[(r["pnl"][e] if r.get("pnl") else -0.0005) for e in exits] for r in R])
    Bv = np.array([r["B"] for r in R])
    Fm = {k: np.array([r.get(k, 0) if r.get(k) is not None else 0 for r in R], float) for k in feats}
    out = []
    names = list(grid)
    for combo in itertools.product(*[grid[k] for k in names]):
        m = np.ones(len(R), bool)
        for k, (lo, hi) in zip(names, combo):
            if lo is not None: m &= Fm[k] >= lo
            if hi is not None: m &= Fm[k] < hi
        m2 = m & (run == "R2"); m3 = m & (run == "R3")
        n2 = int(m2.sum()); n3 = int(m3.sum())
        if n2 < minN: continue
        s2 = P[m2].sum(0); s3 = P[m3].sum(0); v2 = Bv[m2].sum(); v3 = Bv[m3].sum()
        for j, e in enumerate(exits):
            out.append(dict(rule={k: v for k, v in zip(names, combo)}, exit=e, n2=n2, pnl2=round(float(s2[j]), 3), per2=round(float(s2[j]) / max(v2, 1e-9), 4),
                            n3=n3, pnl3=round(float(s3[j]), 3), per3=round(float(s3[j]) / max(v3, 1e-9), 4)))
    out.sort(key=lambda o: -o["pnl2"])
    base = dict(n2=int((run == "R2").sum()), n3=int((run == "R3").sum()),
                all2={e: round(float(P[run == "R2"][:, j].sum()), 2) for j, e in enumerate(exits)},
                all3={e: round(float(P[run == "R3"][:, j].sum()), 2) for j, e in enumerate(exits)})
    return dict(top=out[:15], base=base, n_rules=len(out),
                r3_of_top20=[(o["pnl2"], o["pnl3"], o["n3"]) for o in out[:20]],
                share_top20_pos_r3=sum(1 for o in out[:20] if o["pnl3"] > 0) / max(1, min(20, len(out))))
N = None
# F7 quiet bait (substitution, no race)
res["Q"] = evaluate("Q", 0, ["vpre", "quiet", "age", "ath_r", "peakv", "sz"], {
    "vpre": [(None, 33), (None, 35), (None, 40), (None, 46)],
    "quiet": [(20, None), (50, None), (150, None), (500, None)],
    "age": [(150, 1500), (1500, None), (150, None)],
    "ath_r": [(None, None), (None, 0.7), (0.9, None)],
    "peakv": [(None, None), (40, None), (50, None)]}, 60)
# F6 momentum (+ F4-style 4-slot exit) at 35 and 50 ms
for lat in (35, 50):
    res[f"M{lat}"] = evaluate("M", lat, ["sz", "vpre", "ret10", "flow", "age"], {
        "sz": [(0.5, None), (1.0, None), (2.0, None)],
        "vpre": [(33, 45), (45, 60), (33, 60)],
        "ret10": [(0.1, None), (0.2, None), (0.3, None)],
        "flow": [(1, None), (2, None), (4, None)],
        "age": [(None, 25), (25, 300), (300, None), (None, None)]}, 100)
# F3 / F1 dips at 35 and 50 ms
for lat in (35, 50):
    res[f"D{lat}"] = evaluate("D", lat, ["sz", "dd", "dev", "age", "vpre"], {
        "sz": [(0.5, None), (1.0, None), (2.0, None)],
        "dd": [(0.05, None), (0.10, None), (0.15, None)],
        "dev": [(None, None), (1, None), (None, 1)],
        "age": [(25, 100), (100, 344), (344, 1500), (1500, None), (25, 344)],
        "vpre": [(30, 45), (45, 60), (30, 60)]}, 100)
# F7 natural experiment: the F7 wallets' own trigger buys vs everyone else's (all Q events, same exits)
Q = [r for r in rows if r["kind"] == "Q"]
def summ(rs):
    if not rs: return None
    ex = list(rs[0]["pnl"]); v = sum(r["B"] for r in rs)
    return dict(n=len(rs), vol=round(v, 1), **{e: round(sum(r["pnl"][e] for r in rs), 2) for e in ex})
res["Q_by_who"] = {"F7_members_R2": summ([r for r in Q if r["u"] in F7W and r["run"] == "R2"]), "F7_members_R3": summ([r for r in Q if r["u"] in F7W and r["run"] == "R3"]),
                   "others_R2": summ([r for r in Q if r["u"] not in F7W and r["run"] == "R2"]), "others_R3": summ([r for r in Q if r["u"] not in F7W and r["run"] == "R3"])}
json.dump(res, open(f"{OUT}/replay_select.json", "w"), indent=1)
for k, v in res.items():
    if k == "Q_by_who":
        print("\nQ events by who (sum P&L per exit, SOL):")
        for kk, vv in v.items(): print("  ", kk, vv)
        continue
    if not v: continue
    print(f"\n== {k}: events R2 {v['base']['n2']} R3 {v['base']['n3']}; rules scored {v['n_rules']}; R3 positive among top-20 R2 rules: {v['share_top20_pos_r3']:.0%}")
    print("   unfiltered R2:", v["base"]["all2"]); print("   unfiltered R3:", v["base"]["all3"])
    for o in v["top"][:6]:
        print(f"   R2 {o['pnl2']:+8.2f} ({o['n2']:5d}, {o['per2']:+.3f}/SOL) -> R3 {o['pnl3']:+8.2f} ({o['n3']:5d}, {o['per3']:+.3f}/SOL)  {o['exit']:<20} {o['rule']}")
