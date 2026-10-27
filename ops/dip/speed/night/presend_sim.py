#!/usr/bin/env python3
# PRE-SEND (limit-order spam) simulation on 7 h of chain, READ-ONLY. For every "hot" token-slot (>= HOTFLOW SOL bought in the last 15 s,
# curve 25-60 SOL, token <= MAXAGE s old), we send K cheap buys built at the slot's start price P0; each executes at a uniformly random
# position in the block (0..block's last pump index). It fills only if the curve price there <= P0 x (1 - D) (min_out); else it fails and
# costs 0.0000051 SOL (5k2Ckkiu's measured average). Fill: 0.3 SOL, 1.25% pump fee per side, exit at the curve 3 slots later, 20% gain cut.
# One position per token at a time.
import json, collections, bisect, random, sys
rows = json.load(open("race_rows.json")); random.seed(3)
T = collections.defaultdict(list); first = {}; mx = collections.defaultdict(int)
for r in rows:
    mx[r[0]] = max(mx[r[0]], r[1])
    if r[4]:
        for t in r[11]:
            if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[3], t[1], t[5], t[6])); first.setdefault(t[0], r[0])
hours = (rows[-1][0] - rows[0][0]) * 0.2126 / 3600
S = 0.3e9; FEE = 0.0125; TXF = 0.0000051
def run(D, K, HOT, MAXAGE):
    pnl = 0; fills = 0; sends = 0; wins = 0
    for m, v in T.items():
        v.sort(); keys = [(x[0], x[1]) for x in v]; slots = sorted({x[0] for x in v}); busy = -1
        for s in slots:
            if s <= busy: continue
            k0 = bisect.bisect_left(keys, (s, 0))
            if k0 == 0: continue
            prev = v[k0 - 1]                                   # state at the slot start
            a15 = bisect.bisect_left(keys, (s - 70, 0))
            flow = sum(x[3] for x in v[a15:k0] if x[2]) / 1e9
            if flow < HOT or not (25e9 <= prev[4] <= 60e9) or (s - first[m]) * 0.2126 > MAXAGE: continue
            p0 = prev[4] / prev[5]; sends += K
            for _ in range(K):
                pos = random.randint(0, max(mx[s], 1))
                ke = bisect.bisect_left(keys, (s, pos)) - 1; e = v[ke]
                if e[4] / e[5] > p0 * (1 - D): pnl -= TXF; continue
                x = S * (1 - FEE); q = e[5] * x / (e[4] + x)
                xv = v[bisect.bisect_left(keys, (s + 4, 0)) - 1]
                out = (xv[4] + x) * q / xv[5] * (1 - FEE); p = (out - S) / 1e9 - 0.0006
                pnl += p * 0.8 if p > 0 else p; fills += 1; wins += p > 0; busy = s + 3; break
    return pnl, fills, sends
print(f"window {hours:.1f} h")
for HOT, MAXAGE in ((10, 60), (25, 60), (10, 600)):
    for D in (0.05, 0.08, 0.12, 0.18):
        for K in (2, 4):
            pnl, fills, sends = run(D, K, HOT, MAXAGE)
            print(f"hot>= {HOT:2d} SOL/15s age<= {MAXAGE:3d}s | limit -{D:.0%} | {K} txs/slot | sends {sends:7d} (fees {sends*TXF:.2f}) | fills {fills:4d} ({fills/hours:4.0f}/h) | NET {pnl:+6.2f} SOL = {pnl/hours*24:+6.1f} SOL/day")
