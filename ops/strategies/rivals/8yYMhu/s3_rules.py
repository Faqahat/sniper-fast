#!/usr/bin/env python3
"""8yYMhu s3 (read-only): can a simple on-chain rule (or a GBDT on the same features) reproduce his selection?
Universe = outside sells >= 1 SOL (uni2.npz). Train 10-25 13:00 -> 10-27 20:00 PKT, TEST 10-27 20:00 -> 10-29 00:50 PKT (unseen).
Paper P&L = r_e73_9 (0.75 SOL in ~37 ms after the sell, out at +9 slots, his own trades removed, after pump fees, before tx costs).
Acid test: rule picks that he did NOT take must also earn. Out: DATA/s3.txt"""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, gbdt_np as G
U = dict(np.load(f"{X.D}/uni2.npz"))
tk = U["taken"] > 0; fl = U["filled"] > 0
tr = U["bt"] < X.W0; te = ~tr
r = U["r_e73_9"]; ok = ~np.isnan(r) & ~U["mayhem"]
COST = 0.0035          # INFERRED per-fill tx cost for a 0.75 SOL copy (his measured fee+tip+failed ~ 1.4 mSOL/lot + margin for a worse lander)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
days_tr = (X.W0 - 1792915200) / 86400; days_te = (1793220600 - X.W0) / 86400
P(f"train {tr.sum()} sells ({days_tr:.2f} d), test {te.sum()} ({days_te:.2f} d); his takes train {(tk&tr).sum()} test {(tk&te).sum()}")
def ev(m, lab):
    res = {}
    for nm, w, d in (("train", tr, days_tr), ("test", te, days_te)):
        s = m & w & ok
        pk = s.sum(); his = (s & tk).sum(); nh = s & ~tk
        pnl = (r[s] - COST).sum(); pnl_nh = (r[nh] - COST).sum()
        res[nm] = (pk, his, pnl, pnl_nh)
        P(f"   {lab:58} {nm:5}: picks/day {pk/d:7.0f}  his share of picks {100*his/max(pk,1):5.1f}%  recall of his takes {100*his/max((tk&w&ok).sum(),1):5.1f}%  "
          f"paper {1000*np.mean(r[s]) if pk else float('nan'):+6.1f} mSOL/pick  P&L/day after {COST*1000:.1f} mSOL cost {pnl/d:+7.2f}  | NOT-his picks {nh.sum()/d:6.0f}/day {1000*np.mean(r[nh]) if nh.sum() else float('nan'):+6.1f} mSOL -> {pnl_nh/d:+7.2f}/day")
    return res
P("\n== baselines ==")
ev(np.ones_like(tk), "all >=1 SOL sells")
ev(tk, "HIS takes (paper, his trades removed)")
eu = np.isin(U["area"], ["DE", "NL", "EU-other"])
ev(eu, "EU leader only")
P("\n== simple rule grid (train-selected by paper P&L/day, then TEST) ==")
grid = dict(drop=[0.05, 0.08, 0.12, 0.18], sol=[1, 2, 3], vmax=[40, 50, 70, 1e9], agemax=[50, 150, 1000, 1e9], sup=[0, 2, 3, 5], nbmax=[100, 300, 1e9], b10=[0, 2, 5])
res = []
for drop, sol, vmax, agemax, sup, nbmax, b10 in itertools.product(*grid.values()):
    m = eu & (U["drop"] >= drop) & (U["sol"] >= sol) & (U["vsol_after"] <= vmax) & (U["age_slots"] <= agemax) & (U["age_slots"] >= 0) & \
        (U["seller_supply_pct"] >= sup) & (U["n_before"] <= nbmax) & (U["buy10"] >= b10)
    s = m & tr & ok
    if s.sum() < 300: continue
    res.append(((r[s] - COST).sum() / days_tr, (drop, sol, vmax, agemax, sup, nbmax, b10), m))
res.sort(key=lambda x: -x[0])
for pnl, par, m in res[:8]:
    P(f" rule drop>={par[0]} sol>={par[1]} vsol<={par[2]} age<={par[3]} supply%>={par[4]} trades_before<={par[5]} buy10>={par[6]} (EU leader): train {pnl:+.2f}/day")
    ev(m, "  -> evaluated")
P("\n== GBDT imitation (predict his takes from on-chain features), top-K by score on TEST ==")
F = ["sol", "drop", "vsol_after", "age_slots", "seller_supply_pct", "seller_frac", "seller_hold_slots", "seller_rank", "dd_peak", "buy10", "sell10",
     "n_before", "n10", "frac", "seller_creator", "seller_cslot"]
Xm = np.column_stack([U[f].astype(float) for f in F] + [eu.astype(float)])
Bm = G.binize(Xm, tr)
y = tk.astype(float)
rng = np.random.default_rng(1); va = tr & (rng.random(len(y)) < 0.2); trn = tr & ~va
trees, f = G.fit(Bm, y, trn, va, rounds=400, lr=0.08, depth=4)
P(f"imitation AUC train {G.auc(y[tr], f[tr]):.3f}  TEST {G.auc(y[te], f[te]):.3f}  (trees {len(trees)})")
acc = np.zeros(Xm.shape[1])
for t in trees: G.imp(t, acc)
P("importance: " + ", ".join(f"{n} {v/acc.sum():.2f}" for n, v in sorted(zip(F + ['eu_leader'], acc), key=lambda kv: -kv[1])[:10]))
for q in (0.99, 0.98, 0.96, 0.94, 0.90):
    th = np.quantile(f[tr], q)
    ev(f >= th, f"imitation score top {100*(1-q):.0f}% (threshold from train)")
P("\n== GBDT profit model (predict paper r>0) trained on train, top-K on TEST ==")
y2 = (r > COST).astype(float); okk = ok
trees2, f2 = G.fit(Bm, y2, trn & okk, va & okk, rounds=400, lr=0.08, depth=4)
P(f"profit-model AUC train {G.auc(y2[tr&okk], f2[tr&okk]):.3f} TEST {G.auc(y2[te&okk], f2[te&okk]):.3f}")
for q in (0.995, 0.99, 0.98, 0.96):
    th = np.quantile(f2[tr & okk], q)
    ev(f2 >= th, f"profit score top {100*(1-q):.1f}% (threshold from train)")
np.savez_compressed(f"{X.D}/s3_scores.npz", imit=f, prof=f2)
open(f"{X.D}/s3.txt", "w").write("\n".join(out) + "\n")
