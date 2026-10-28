#!/usr/bin/env python3
"""EXIT step 18 (read-only): haqq's behind-crowd DIP lots (price paid > 1.05 x post-dump price, analyst B's split) x 'added to
later': actual tape P&L vs exact replay of the lot alone under his exit (ACT), a 5-slot timer, and the causal wave exits
RIDE(S, tmax) from his minimum hold (slot+2) with his reaction delay. %/SOL of cost. MEASURED tape; replays INFERRED.
Out: haqq_dissect/exit/x18.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
QS = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
R, MI, span, CC = X.tape()
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); L = Z["lots"]; POS = Z["pos"]
A = np.load(f"{X.OUT}/paths.npz"); off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; BU = A["buy"]; VX = A["vx"]; VX9 = A["vx9"]
dmy = np.percentile([l["d_ms"] for l in L if l["t"] == "DIP" and l.get("d_ms") is not None], QS)
pols = [("ACT",), ("T", 5), ("T", 30), ("RIDE", 300, 5000), ("RIDE", 1000, 5000), ("RIDE", 1000, 20000)]
acc = collections.defaultdict(lambda: collections.defaultdict(float))
for p in POS:
    i = p["lots"][0]; l = L[i]
    if l["t"] != "DIP" or l.get("d_k") is None or l["close_cc"] is None: continue
    a0 = l["row"] - l["k"]
    px_paid = float(R["sol"][l["row"]]) / max(float(R["tok"][l["row"]]), 1)
    dr = a0 + l["d_k"]; px_post = float(R["vsol"][dr]) / max(float(R["vtok"][dr]), 1)
    pr = px_paid / px_post
    g = ("behind" if pr > 1.05 else "front") + (" / added" if p["nb"] > 1 else " / never added")
    a, b = off[i], off[i + 1]; n = b - a
    if n == 0: continue
    e = ex[i]; inside = 0 < e < n
    dc = DCC[a:b].astype(np.float64); bt = dc[BU[a:b]]
    t2 = 2 * X.SMS - (l["cc"] - l["slot"] * X.SMS)
    acc[g]["n"] += 1; acc[g]["cost"] += l["cost"]; acc[g]["real"] += l["pnl"]
    for fol, V in ((1.0, VX), (0.9, VX9)):
        v = V[a:b].astype(np.float64)
        def at(t): return float(np.mean([v[q] if q >= 0 else 0.975 for q in (np.searchsorted(dc, t + dmy, side="right") - 1)]))
        for pol in pols:
            if pol[0] == "ACT": val = (v[e - 1] - 1) * l["cost"] if inside else l["pnl"]
            elif pol[0] == "T": val = (at(pol[1] * X.SMS - (l["cc"] - l["slot"] * X.SMS)) - 1) * l["cost"]
            else:
                _, s, tm = pol
                rec = bt[(bt <= t2) & (bt > t2 - s)]
                if not len(rec): tt = t2
                else:
                    later = bt[bt > t2 - s]; gaps = np.diff(np.concatenate([later, [np.inf]])); j = int(np.argmax(gaps >= s)); tt = max(later[j] + s, t2)
                val = (at(min(tt, tm)) - 1) * l["cost"]
            acc[g][(pol, fol)] += val
P("# haqq DIP first lots: behind-crowd (paid > 1.05 x post-dump) x added later; %/SOL of cost (full followers; [10% fewer])")
P("| group | lots | real (tape) | " + " | ".join(str(p) for p in pols) + " |"); P("|---|---|---|" + "---|" * len(pols))
for g in ("front / never added", "front / added", "behind / never added", "behind / added"):
    d = acc[g]
    if not d["n"]: continue
    P(f"| {g} | {int(d['n']):,} | {100 * d['real'] / d['cost']:+.2f} | " + " | ".join(f"{100 * d[(p, 1.0)] / d['cost']:+.2f} [{100 * d[(p, 0.9)] / d['cost']:+.2f}]" for p in pols) + " |")
open(f"{X.OUT}/x18.txt", "w").write("\n".join(out) + "\n")
