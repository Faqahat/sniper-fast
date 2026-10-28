#!/usr/bin/env python3
"""LIM step 13 (read-only): compact per-day x server table of the guard counterfactual on our live regular fires
(exit = run's own; net of costs), delta vs live +5% with a 90% bootstrap per row; fol 1.0 (and 0.8 for 'none').
Out: data/lim/l13.txt"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
CF, CX = 3.52e-3, 0.53e-3
net = lambda r, g, fo=1.0: (r["pn"][(r["hold"], fo)] - CF) if r["need"] <= 1 + g + 1e-9 else -CX
R = [r for r in pickle.load(open(f"{OUT}/fires_cf.pkl", "rb")) if not r["mayhem"]]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
def ci(v):
    v = np.asarray(v); g = np.random.default_rng(9); b = [v[g.integers(0, len(v), len(v))].sum() for _ in range(2000)]
    return f"{v.sum():+.2f} [{np.percentile(b,5):+.2f}..{np.percentile(b,95):+.2f}]"
P("| day | srv | fires | live fills | live net SOL | +3.5% delta | +10% delta | +20% delta | no guard delta | no guard delta, 20% fewer followers |")
P("|---|---|---|---|---|---|---|---|---|---|")
for d in sorted({r["day"] for r in R}) + ["all"]:
    for s in ("FRA", "AMS", "both"):
        v = [r for r in R if (d == "all" or r["day"] == d) and (s == "both" or r["srv"] == s)]
        if not v: continue
        dl = lambda g, fo=1.0: [net(r, g, fo) - net(r, 0.05, fo) for r in v]
        P(f"| {d if d == 'all' else L.day_name(d)[:9]} | {s} | {len(v)} | {sum(r['out']=='fill' for r in v)} | {sum(net(r,0.05) for r in v):+.2f} | {ci(dl(0.035))} | {ci(dl(0.10))} | {ci(dl(0.20))} | {ci(dl(9.0))} | {ci(dl(9.0,0.8))} |")
open(f"{OUT}/l13.txt", "w").write("\n".join(out) + "\n")
