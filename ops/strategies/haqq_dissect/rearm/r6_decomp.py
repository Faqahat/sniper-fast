#!/usr/bin/env python3
"""REARM step 6 (read-only): where do re-arm fills come from and why does the engine-faithful replay disagree with analyst A's
proxy (+41.5 mSOL/fill model)? For one res file and config, re windows split by:
  * fill on the NEXT WHALE DUMP (fill slot = the whale dump's slot or the next) vs a fill on another >= 12 % drop (a cascade of
    smaller sells, the paid dump's aftermath, a dev sell...) vs no fill;
  * windows that saw a next whale dump inside them: our fill share on it and the per-fill value.
P&L = gross (live exit) - NOW costs, model level, mSOL per fill; 90 % bootstrap over fills.
usage: r6_decomp.py TAG CFG DAY[,DAY]"""
import sys, pickle, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = 2_015_140


def boot(v, n=2000):
    v = np.asarray(v, float)
    if len(v) < 2: return (np.nan, np.nan)
    r = np.random.default_rng(1); m = [v[r.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return np.percentile(m, 5), np.percentile(m, 95)


tag, cfg, days = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",")]
G = collections.defaultdict(list); nwin = collections.Counter(); wsin = 0; wsfill = 0
for d in days:
    Z = pickle.load(open(f"{OUT}/res_D{d}_{tag}.pkl", "rb"))
    for r in Z["out"][cfg][0]:
        key = r[0]
        if key[0] != "re" or not r[1]: continue
        ws = key[5]; en = None
        has_ws = ws is not None
        nwin["armed"] += 1
        if has_ws: nwin["next whale dump exists"] += 1
        if not r[3]: continue
        fS = r[8][0]; g = (r[8][2]["base"][0] - COST) / 1e6; gw = (r[8][2]["wave"][0] - COST) / 1e6
        cls = "on the next whale dump" if has_ws and ws[0] <= fS <= ws[0] + 1 else ("before the next whale dump" if has_ws and fS < ws[0] else "no whale dump (other >= 12% drop)")
        G[cls].append((g, gw, r[8][2]["base"][1]))
print(f"# {tag} {cfg} days {days}: re windows armed {nwin['armed']:,}; with a next whale dump on the token (any time) {nwin['next whale dump exists']:,}")
print("| Fill class | Fills | mSOL/fill model NOW [90%] | win | wave exit mSOL/fill | exits (tp/sl/time) |")
print("|---|---|---|---|---|---|")
for k, v in G.items():
    a = np.array([x[0] for x in v]); b = np.array([x[1] for x in v]); lo, hi = boot(a)
    c = collections.Counter(x[2] for x in v)
    print(f"| {k} | {len(v)} | {a.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] | {100 * (a > 0).mean():.0f}% | {b.mean():+.2f} | {c.get('tp', 0)}/{c.get('sl', 0)}/{c.get('time', 0)} |")
