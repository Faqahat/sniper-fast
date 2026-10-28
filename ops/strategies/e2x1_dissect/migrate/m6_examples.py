#!/usr/bin/env python3
"""migrate agent, step 6: per-entry listing for one variant (tag V horizon theta exit-index [days]) with GMGN links; also the
cost sensitivity (try cost 0.3 mSOL instead of 0.005) and the 35 ms landing variant for the same rule.
Usage: m6_examples.py TAG V HOR THETA XI"""
import sys, pickle, numpy as np
from mlib import D, TRAIN, TEST, pkt
tag, V, hor, th, xi = sys.argv[1], int(sys.argv[2]), sys.argv[3], float(sys.argv[4]), int(sys.argv[5])
F = pickle.load(open(D + "/feat.pkl", "rb")); meta = F["meta"]; PP = pickle.load(open(D + "/feat_p.pkl", "rb"))
def load(t):
    S = pickle.load(open(D + f"/sim_{t}.pkl", "rb")); R = S["R"]; I = np.array([r["i"] for r in R]); return S, R, I
S, R, I = load(tag); EX = S["EXITS"]
sel = [(r, meta[r["i"]]) for r in R if meta[r["i"]]["V"] == V and meta[r["i"]]["ncross"] == 0 and PP[hor][r["i"]] >= th]
print(f"variant {tag} V={V} {hor}>={th} exit {EX[xi]}: {len(sel)} candidate rows")
for ds, nm in ((TRAIN, "train"), (TEST, "test")):
    a = [(r, m) for r, m in sel if m["day"] in ds]
    tot = sum(r["res"][xi] for r, m in a); tr = sum(r["tries"] for r, m in a)
    print(f"  {nm}: {tot / len(ds):+.2f}/day; tries {tr / len(ds):.0f}/day -> with 0.3 mSOL per landed try instead of 0.005: {(tot - tr * 0.000295) / len(ds):+.2f}/day")
if tag == "react_1.0":
    try:
        S2, R2, I2 = load("react_1.0_35ms"); d2 = {r["i"]: r for r in R2}
        for ds, nm in ((TRAIN, "train"), (TEST, "test")):
            a = [d2[r["i"]] for r, m in sel if m["day"] in ds and r["i"] in d2]
            print(f"  35 ms landing, {nm}: {sum(r['res'][xi] for r in a) / len(ds):+.2f}/day")
    except FileNotFoundError: pass
print("\nTEST entries sorted by P&L (expected over 10 landing samples); grad = token graduated; fill = share of samples filled")
rows = sorted([(r["res"][xi], r, m) for r, m in sel if m["day"] in TEST], key=lambda x: -x[0])
for v, r, m in rows[:8] + [("...", None, None)] + rows[-6:]:
    if r is None: print("  ..."); continue
    print(f"  {v:+.3f}  {pkt(m['bt']).strftime('%m-%d %H:%M:%S')} PKT  grad={int(m['grad'])} fill={r['fill']:.1f} p={PP[hor][r['i']]:.2f} t_complete={m['t_complete'] if np.isfinite(m['t_complete']) else 'never'}  https://gmgn.ai/sol/token/{m['mint']}")
top = sorted([(r["res"][xi], m["day"]) for r, m in sel if m["day"] in TEST], reverse=True)
print(f"\ntest: top-5 trades sum {sum(v for v, d in top[:5]):+.2f} of total {sum(v for v, d in top):+.2f}")
