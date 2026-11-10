#!/usr/bin/env python3
"""LEADFOL placebo / persistence checks on 10-31 (K=25, D=70):
 (a) all qualifying buys; (b) active wallets n>=30 every fit day, NO P&L criterion; (c) n>=30 and mean < 0 every fit day;
 (d) n>=30 and mean >= 0 (= the rule); (e) rank correlation fit mean vs 10-31 mean for wallets active on all 4 days"""
import numpy as np
import nlib as L
from n5_scan import ev, one_pos
FIT = L.RUNS[:3]; CH = L.RUNS[3]; K = 25
key = f"d70k{K}"
per = []
for r in FIT:
    d = ev(r); names = d["users"][d["u"]]
    uu, inv = np.unique(names, return_inverse=True)
    n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
    per.append({u: (n[j], s[j]) for j, u in enumerate(uu)})
act = set.intersection(*[set(u for u, (n, s) in p.items() if n >= 30) for p in per])
pos = set(u for u in act if all(p[u][1] >= 0 for p in per)); neg = set(u for u in act if all(p[u][1] < 0 for p in per))
d = ev(CH); names = d["users"][d["u"]]; hrs = d["hours"]
def sc(msk, lab):
    idx = np.nonzero(msk)[0]; idx = idx[one_pos(d["m"][idx], d["cc"][idx], K, 70)]
    v = d[key][idx].astype(np.float64); s = L.stats(v)
    print(f"{lab}: n {s['n']} mSOL/trip {s['per']:+.1f} SOL/day {s['net']/hrs*24:+.1f} win {s['win']} wo5 {s['wo5']:+.2f}")
sc(np.ones(len(names), bool), "(a) all buys")
sc(np.isin(names, list(act)), f"(b) active n>=30 all fit days ({len(act)} wallets)")
sc(np.isin(names, list(neg)), f"(c) active & mean<0 all fit days ({len(neg)})")
sc(np.isin(names, list(pos)), f"(d) active & mean>=0 all fit days ({len(pos)})")
mix = act - pos - neg
sc(np.isin(names, list(mix)), f"(e) active, mixed sign ({len(mix)})")
uu, inv = np.unique(names, return_inverse=True); n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
c = {u: s[j] / n[j] for j, u in enumerate(uu) if n[j] >= 10}
xs = [(sum(p[u][1] for p in per) / sum(p[u][0] for p in per), c[u]) for u in act if u in c]
a = np.array(xs)
from scipy.stats import spearmanr
print("wallets active all 4 days:", len(a), "spearman fit-mean vs 10-31 mean:", spearmanr(a[:, 0], a[:, 1]))
