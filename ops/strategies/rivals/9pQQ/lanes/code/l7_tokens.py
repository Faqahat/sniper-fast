#!/usr/bin/env python3
"""LANES step 7: token-level table for PATH A (new-token first entry). For every non-mayhem recorded launch:
state at ages 8 / 10 / 15 / 20 / 30 / 50 slots (vsol, n trades, n buys, n sells, unique buyers, buy SOL, sell SOL, max single buy, dev buy SOL, create-slot buyers),
first 9pQQ buy (age, slot, idx).  -> lanes/tokens_<run>.pkl.  usage: l7_tokens.py RUN"""
import sys, pickle, numpy as np, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
run = sys.argv[1]; K, V = llib.K, llib.V
t = llib.load(run); L = llib.launches(run)
def vs(c): return K / (np.asarray(c, float) + V)
rows = []
for mint, la in L.items():
    if la["may"] or mint not in t.mix: continue
    m = t.mix[mint]; a, b = t.ms[m], t.ms[m + 1]
    S = t.s[a:b] - la["slot"]; U = t.u[a:b]; DV = (vs(t.cpost[a:b]) - vs(t.cpre[a:b])) / 1e9; CP = t.cpost[a:b]
    own = np.nonzero(U == t.wid)[0]
    r = dict(run=run, mint=mint, creator=la["creator"], ntr=int(b - a))
    fb = own[DV[own] > 0][0] if len(own) and (DV[own] > 0).any() else None
    r["fb_age"] = int(S[fb]) if fb is not None else None
    # dev buy = trades by creator at age 0
    cr = np.searchsorted(t.users, la["creator"]); cr = cr if cr < len(t.users) and t.users[cr] == la["creator"] else -1
    r["dev_sol"] = float(DV[(U == cr) & (S == 0) & (DV > 0)].sum())
    r["slot0_buyers"] = int(len(set(U[(S == 0) & (DV > 0) & (U != cr)])))
    r["slot0_sol"] = float(DV[(S == 0) & (DV > 0) & (U != cr)].sum())
    for A in (8, 10, 15, 20, 30, 50, 100):
        sel = (S < A) & (U != t.wid)
        k = np.nonzero(S < A)[0]
        r[f"vsol{A}"] = float(vs(CP[k[-1]])) / 1e9 if len(k) else 30.0
        r[f"n{A}"] = int(sel.sum()); r[f"nb{A}"] = int((sel & (DV > 0)).sum()); r[f"ns{A}"] = int((sel & (DV < 0)).sum())
        r[f"ub{A}"] = int(len(set(U[sel & (DV > 0)]))); r[f"bsol{A}"] = float(DV[sel & (DV > 0)].sum()); r[f"ssol{A}"] = float(-DV[sel & (DV < 0)].sum())
        r[f"mxb{A}"] = float(DV[sel].max()) if sel.any() else 0.0
        r[f"devsold{A}"] = bool(((U == cr) & (DV < 0) & (S < A)).any())
        r[f"vmax{A}"] = float(vs(CP[k].min())) / 1e9 if len(k) else 30.0
    rows.append(r)
pickle.dump(rows, open(f"{llib.D}/tokens_{run}.pkl", "wb"))
print(run, len(rows), sum(r["fb_age"] is not None for r in rows), flush=True)
