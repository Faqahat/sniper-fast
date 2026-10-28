#!/usr/bin/env python3
"""select2 t8: for the top-10 features of the ALL model, 5 example picks (his buys, preferring TEST day) where the feature is in
its 'his' direction (feature higher among his picks than among negatives => top quintile, else bottom), with GMGN token links,
trigger wallet, time (PKT), feature value, sim P&L. Out: OUT/examples.md (pasted into REPORT.md)"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
U = dict(np.load(f"{OUT}/U2.npz")); SIM = dict(np.load(f"{OUT}/sim_66.npz")); MN, US = names()
R = json.load(open(f"{OUT}/t6_main.json")); imp = R["models"]["ALL"]["imp"][:10]
y = U["y"].astype(bool); samp = U["samp"].astype(bool); TE = U["bt"] >= R["TCUT"]
DESC = json.load(open(f"/home/moiz/sniper/ops/strategies/e2x1_dissect/select2/feature_desc.json"))
lines = []
rng = np.random.default_rng(0)
for f, g in imp:
    v = U[f] if f in U else None
    if v is None: lines.append(f"### {f} — (derived in t6, no raw column)\n"); continue
    hi = np.nanmean(v[y]) > np.nanmean(v[samp & ~y]); direction = "high" if hi else "low"
    q = np.nanquantile(v[y], 0.8 if hi else 0.2)
    cand = np.flatnonzero(y & TE & ((v >= q) if hi else (v <= q)))
    if len(cand) < 5: cand = np.flatnonzero(y & ((v >= q) if hi else (v <= q)))
    pick = rng.choice(cand, min(5, len(cand)), replace=False)
    lines.append(f"### {f} (gain share {g:.3f}) — {DESC.get(f, '')}\n- His picks have {direction}er values (median his {np.nanmedian(v[y]):.4g} vs others {np.nanmedian(v[samp & ~y]):.4g}).\n")
    lines.append("| time PKT | token | trigger wallet | trigger | age s | value | g94 % | sim 34 s mSOL |\n|---|---|---|---|---|---|---|---|")
    for r in pick:
        m = MN[int(U["mint"][r])]; u = US[int(U["user"][r])]
        lines.append(f"| {pkt(U['bt'][r])} | [{m[:6]}](https://gmgn.ai/sol/token/{m}) | [{u[:8]}](https://gmgn.ai/sol/address/{u}) | {'buy' if U['is_buy'][r] else 'sell'} {U['sol'][r]:.2f} SOL ({100*U['imp'][r]:+.1f}%) | {U['age_s'][r]:.0f} | {v[r]:.4g} | {100*U['g94'][r]:+.1f} | {1000*SIM['tier|34s|0.2|pnl'][r]:+.1f} |")
    lines.append("")
open(f"{OUT}/examples.md", "w").write("\n".join(lines)); print("\n".join(lines)[:3000])
