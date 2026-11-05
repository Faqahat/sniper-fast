#!/usr/bin/env python3
"""FLATSIG task 1 [MEASURED, post-hoc labels]: on our live fills, did a competitor dip bot BUY the token after our fill?
Windows: in-hold (engine tape, ms clock: our first buy -> our last sell landing), and on the raw chain: same slot after our buy,
<= +1, +2, +5, +25 slots (slot ~ 400 ms). Bot sets: NAMED (owner's list + dissections), COH (DEV-fit data-driven cohort, f5).
Prints flat / win rates and mean P&L per period, with and without a bot buy, plus the 'nobody bought' baseline.
Out: /home/moiz/sniper-data/flatsig/t1.json (per position labels)"""
import numpy as np, json, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L
D = L.D
z = np.load(f"{D}/chain.npz")
S, I, M, U, B, SOL = z["slot"], z["idx"], z["mint"], z["user"], z["buy"], z["sol"]
COH = np.array(sorted(int(x) for x in json.load(open(f"{D}/cohort.json"))["ids"]), dtype=np.uint64)
NAM = np.array(sorted(L.NAMED64), dtype=np.uint64)
OUR = np.array(sorted(L.OURS64), dtype=np.uint64)
spans = json.load(open(f"{D}/spans.json"))
P = L.all_positions()
lab = {}
for p in P:
    if not any(lo + 50 <= p["buy_slot"] <= hi - 60 for _, lo, hi in spans): continue
    m = np.uint64(L.pk64(p["mint"]))
    a = np.searchsorted(M, m); e = np.searchsorted(M, m, side="right")
    if a == e: continue
    ss, ii, uu, bb = S[a:e], I[a:e], U[a:e], B[a:e]
    after = ((ss > p["buy_slot"]) | ((ss == p["buy_slot"]) & (ii > p["buy_idx"]))) & (bb == 1) & ~np.isin(uu, OUR)
    if p["kind"] == "T2" and p["whale"]: after &= uu != np.uint64(L.pk64(p["whale"]))
    d = {"in_hold_N": any(u in L.NAMED for _, _, u, _, _ in p["fol"]), "in_hold_any": len(p["fol"]) > 0}
    for w in (0, 1, 2, 5, 25):
        mm = after & (ss <= p["buy_slot"] + w)
        d[f"N{w}"] = bool((mm & np.isin(uu, NAM)).any()); d[f"C{w}"] = bool((mm & np.isin(uu, COH)).any()); d[f"A{w}"] = bool(mm.any())
    lab[p["id"]] = d
json.dump({str(k): v for k, v in lab.items()}, open(f"{D}/t1.json", "w"))
print("positions", len(P), "with chain", len(lab))
out = []
for per in L.PERS:
    for key in ["in_hold_N", "in_hold_any", "N0", "N1", "N2", "N5", "N25", "C0", "C1", "C2", "C5", "A2", "A5"]:
        row = []
        for v in (True, False):
            s = [p for p in P if p["per"] == per and p["id"] in lab and lab[p["id"]][key] == v]
            c = collections.Counter(p["cls"] for p in s); k = len(s) or 1
            row.append(f"{str(v)[0]} n={len(s):4d} {sum(p['pnl'] for p in s) / k * 1000:+6.1f}mSOL flat {c['flat'] / k:4.0%} win>=25 {c['win'] / k:4.0%} small {c['small'] / k:4.0%} big {c['bigloss'] / k:4.0%}")
        line = f"{per:4s} {key:11s} | " + " || ".join(row)
        print(line); out.append(line)
open(f"{D}/t1.txt", "w").write("\n".join(out) + "\n")
