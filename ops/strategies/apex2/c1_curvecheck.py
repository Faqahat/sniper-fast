#!/usr/bin/env python3
"""APEX2 check (b): pump.fun curve math vs recorded post-trade reserves. usage: c1_curvecheck.py NPZ [NPZ ...]"""
import sys, numpy as np, collections
T = []; 
for fn in sys.argv[1:]:
    z = np.load(fn, allow_pickle=True); ids = z["ids"]; t = z["trades"]
    T += [(int(r["slot"]), int(r["idx"]), int(r["j"]), ids[r["mint"]], int(r["buy"]), int(r["sol"]), int(r["tok"]), int(r["vsol"]),
           int(r["vtok"]), int(r["fee_bps"]), int(r["cfee_bps"]), int(r["ixk"]), int(r["sd"]), int(r["txfee"]), int(r["tips"])) for r in t]
T.sort()
last = {}; C = collections.Counter(); E = collections.defaultdict(list)
for (s, i, j, m, b, sol, tok, vs, vt, fb, cb, ik, sd, txf, tip) in T:
    p = last.get(m); last[m] = (vs, vt)
    if p is None: continue
    V, Tt = p
    if V == 0 or Tt == 0 or sol == 0 or tok == 0: C["zero"] += 1; continue
    cont = (vs == V + sol and vt == Tt - tok) if b else (vs == V - sol and vt == Tt + tok)
    C["cont_ok" if cont else "cont_bad"] += 1
    if not cont: continue
    if b:
        # fixed-token formula candidates
        a1 = tok * V // (Tt - tok) + 1; a2 = -(-tok * V // (Tt - tok))
        C["buy_n"] += 1; C["buy_floor+1"] += (sol == a1); C["buy_ceil"] += (sol == a2)
        # exact-sol-in: tokens from sol (net): floor(sol*T/(V+sol))
        t1 = sol * Tt // (V + sol); C["buy_tok_floor"] += (tok == t1)
        E["buy_relerr"].append(abs(sol - tok * V / (Tt - tok)) / max(sol, 1))
        # product drift
        E["k_rel"].append(vs * vt / (V * Tt) - 1)
    else:
        a1 = tok * V // (Tt + tok); C["sell_n"] += 1; C["sell_floor"] += (sol == a1)
        E["sell_relerr"].append(abs(sol - tok * V / (Tt + tok)) / max(sol, 1))
        E["k_rel"].append(vs * vt / (V * Tt) - 1)
print(dict(C))
for k, v in E.items():
    v = np.array(v); print(k, "n", len(v), "mean", v.mean(), "p99", np.percentile(np.abs(v), 99), "max", np.abs(v).max())
