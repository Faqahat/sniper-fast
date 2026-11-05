#!/usr/bin/env python3
"""FLATSIG step: DEV-only grid of 1-3 condition SKIP rules from the bot-selection features on our live positions (T2 + re-arm
separately and together). Positions already blocked by QUIET3-A (simulated) are removed first (current live = QUIET + QUIET3-A).
Score = SOL saved = -sum(realized P&L of blocked positions); robustness: saved in each DEV chunk (r37 | r38-r41 | r42<cut),
saved without its 5 biggest saves. Prints the top rules by min(chunk saved)."""
import numpy as np, sys, os, itertools, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L, fpos
P = [p for p in fpos.positions() if p["per"] == "DEV" and "f" in p and not p["q3a"]]
kind = sys.argv[1] if len(sys.argv) > 1 else "T2"
if kind != "all": P = [p for p in P if p["kind"] == kind]
chunk = lambda p: 0 if p["run"] == "r37" else (1 if p["run"] in ("r38", "r39", "r40", "r41") else 2)
print("DEV positions", len(P), "net", round(sum(p["pnl"] for p in P), 3), collections.Counter(chunk(p) for p in P))
F = lambda c: (lambda p: p["f"][c])
conds = []
for c in ["nN_hold", "nC_hold", "nN_prior", "nC_prior", "nN_dist", "nC_dist", "nN_50", "nC_50", "fN_prior"]:
    for t in [0, 1, 2]:
        conds.append((f"{c}<={t}", (lambda c, t: lambda p: p["f"][c] <= t)(c, t)))
for c in ["wh_botN", "wh_botC", "cr_botN"]:
    for t in [0.2, 0.4, 0.5, 0.6]:
        conds.append((f"{c}<={t}(hist)", (lambda c, t: lambda p: 0 <= p["f"][c] <= t)(c, t)))
        conds.append((f"{c}<={t}|nohist", (lambda c, t: lambda p: p["f"][c] <= t)(c, t)))
for c, ts in [("n_120", [6, 12, 24, 40]), ("n_60", [5, 10, 20]), ("buyers", [5, 8, 12, 17]), ("n_10s", [4, 9, 14]),
              ("buy_sol_60", [5, 10, 15]), ("big_sells_60", [0, 1, 2]), ("wh_n", [1, 2, 5]), ("vsol_pre", [33, 35, 37])]:
    for t in ts: conds.append((f"{c}<={t}", (lambda c, t: lambda p: p["f"][c] <= t)(c, t)))
for c, ts in [("max_hold_pct", [6.6, 11, 15]), ("nN_last_age", [60, 150, 1000])]:
    for t in ts: conds.append((f"{c}>={t}", (lambda c, t: lambda p: p["f"][c] >= t)(c, t)))
grp = lambda name: name.split("<")[0].split(">")[0].split("(")[0]
pnl = np.array([p["pnl"] for p in P]); ch = np.array([chunk(p) for p in P])
CM = {n: np.array([f(p) for p in P]) for n, f in conds}
res = []
names = list(CM)
for r in (1, 2, 3):
    for combo in itertools.combinations(names, r):
        if len({grp(x) for x in combo}) < r: continue
        if r == 3 and not any(x.startswith(("nN", "nC", "fN")) for x in combo): continue
        m = np.logical_and.reduce([CM[x] for x in combo])
        n = int(m.sum())
        if n < 25: continue
        b = pnl[m]; saved = -b.sum()
        cs = [-pnl[m & (ch == k)].sum() for k in range(3)]
        wo5 = -np.sort(b)[5:].sum()
        res.append((min(cs), saved, wo5, n, int((b > 0).sum()), int(((b <= 0) & (b >= -0.025)).sum()), cs, combo))
res.sort(key=lambda x: -x[0])
for x in res[:40]:
    print(f"min {x[0]:+.3f} saved {x[1]:+.3f} wo5 {x[2]:+.3f} n {x[3]:3d} winners {x[4]:3d} flats {x[5]:3d} chunks {[round(c,3) for c in x[6]]}  {' & '.join(x[7])}")
json.dump([[x[0], x[1], x[2], x[3], x[4], x[5], x[6], list(x[7])] for x in res[:300]], open(f"{L.D}/grid_{kind}.json", "w"))
print("rules tested", len(res))
