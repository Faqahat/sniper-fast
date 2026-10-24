#!/usr/bin/env python3
# Replay of our mechanics on EVERY tradeable non-SOL launch (no selection) + simple splits. -> base.txt
import sys; sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
from ns_lib import *
import ns
rows = [r for r in load_rows() if tradeable(r)]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1])
P("ALL tradeable non-SOL launches (non-mayhem, dev buy in the create tx), 0.5 SOL-eq, guard 0.5%, swap leg 0.3%, overhead 2%")
for run in ("R1", "R2"):
    rr = [r for r in rows if r["run"] == run]
    for Lm in (30, 45, 75):
        for var in ("base", "strict", "harsh"):
            P(f"{run} L{Lm} {var:6s} " + " || ".join(f"{ex[:-2]}s: {summ(rr, Lm, var, ex)['tot']:+7.1f}" for ex in ("0.0", "2.0", "3.0", "5.0", "8.0", "10.0", "20.0")) + f" || fills {summ(rr, Lm, var)['fills']}/{summ(rr, Lm, var)['n']}")
def qcls(q):
    n = ns.qname(q)
    if n in ("PUMP", "USDC"): return n
    if q.endswith("pump"): return "pump-token"
    if q.startswith("Xs"): return "xStock"
    return "other"
P("\nBy quote class, L45 strict t8 (R1 | R2):")
for qc in ("PUMP", "USDC", "xStock", "pump-token", "other"):
    a = [r for r in rows if qcls(r["quote"]) == qc]
    P(f"  {qc:10s} R1 {fmt(summ([r for r in a if r['run']=='R1'], 45))}\n  {'':10s} R2 {fmt(summ([r for r in a if r['run']=='R2'], 45))}")
P("\nBy dev buy / glued (L45 strict t8):")
for lab, f in (("dev<0.5", lambda r: r["dev_sol"] < 0.5), ("dev 0.5-2", lambda r: 0.5 <= r["dev_sol"] < 2), ("dev>=2", lambda r: r["dev_sol"] >= 2),
               ("glued0", lambda r: r["n_glued"] == 0), ("glued>=1", lambda r: r["n_glued"] >= 1), ("glued>=2 & dev>=1", lambda r: r["n_glued"] >= 2 and r["dev_sol"] >= 1),
               ("cbps<=30", lambda r: r["cbps"] <= 30), ("cbps>=100", lambda r: r["cbps"] >= 100)):
    a = [r for r in rows if f(r)]
    P(f"  {lab:18s} R1 {fmt(summ([r for r in a if r['run']=='R1'], 45))}\n  {'':18s} R2 {fmt(summ([r for r in a if r['run']=='R2'], 45))}")
P("\nORACLE upper bound (not tradeable: look-ahead): launches with generic buy >= 3 SOL-eq in 2-10 s, L45:")
for var in ("base", "strict"):
    for run in ("R1", "R2"):
        a = [r for r in rows if r["run"] == run and r["flow"].get("gen_w2_b", 0) >= 3]
        P(f"  {var:6s} {run} t5 {fmt(summ(a, 45, var, '5.0'))}\n  {'':6s} {run} t8 {fmt(summ(a, 45, var, '8.0'))}")
open("/home/moiz/sniper/ops/overnight/nonsol/base.txt", "w").write("\n".join(out) + "\n")
