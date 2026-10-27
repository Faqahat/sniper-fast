#!/usr/bin/env python3
# "HQ" = haqqiUUX's patterns as rules, replayed at OUR landing (entry = curve just before dump idx + OFF in the dump slot, +5% guard),
# 0.3 SOL, exit after HOLD slots, 1.25% fee per side, 0.002 SOL tx+tips per filled trip, 20% cut of gains (followers priced out).
import json, collections, bisect, statistics, sys
rows = json.load(open("race_rows.json"))
T = collections.defaultdict(list); first = {}
for r in rows:
    if not r[4]: continue
    for t in r[11]:
        if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6], r[13])); first.setdefault(t[0], r[0])
for m in T: T[m].sort()
S = 0.3e9; FEE = 0.0125
def before(v, s, i):
    k = bisect.bisect_left(v, (s, i)) - 1
    return v[k] if k >= 0 else None
def replay(v, s, i, off, hold):
    post = before([(x[0], x[1], x[6], x[7]) for x in v], s, i + 1) if False else None
    keys = [(x[0], x[1]) for x in v]
    kp = bisect.bisect_left(keys, (s, i + 1)) - 1; ke = bisect.bisect_left(keys, (s, i + 1 + off)) - 1
    if kp < 0 or ke < 0: return None
    pv, ev = v[kp], v[ke]
    if (ev[6] / ev[7]) / (pv[6] / pv[7]) > 1.05: return -0.0005
    x = S * (1 - FEE); q = ev[7] * x / (ev[6] + x)
    kx = bisect.bisect_left(keys, (s + hold + 1, 0)) - 1; xv = v[kx]
    out = (xv[6] + x) * q / xv[7] * (1 - FEE); p = (out - S) / 1e9 - 0.002
    return p * 0.8 if p > 0 else p
def rules(v, k, R):
    x = v[k]; s = x[0]; slots = [y[0] for y in v]
    a5 = bisect.bisect_left(slots, s - 24); a15 = bisect.bisect_left(slots, s - 70)
    age = (s - first[x[0] and v[0][0]] if False else (s - v[0][0])) * 0.2126
    drop = 1 - (x[6] / x[7]) / ((x[6] + x[4]) / max(x[7] - x[5], 1))
    b5 = len({y[2] for y in v[a5:k] if y[3]})
    return (age <= R["age"] and R["c0"] <= x[6] / 1e9 <= R["c1"] and drop >= R["drop"] and b5 >= R["b5"])
hours = (rows[-1][0] - rows[0][0]) * 0.2126 / 3600
VAR = {"HQ core": dict(age=10, c0=25, c1=45, drop=0.06, b5=5), "HQ wide": dict(age=30, c0=25, c1=60, drop=0.05, b5=3), "HQ strict": dict(age=10, c0=25, c1=45, drop=0.10, b5=10)}
bt_mid = None
for name, R in VAR.items():
    for off in (40, 80, 120):
        for hold in (6, 9):
            vals = []
            for m, v in T.items():
                for k, x in enumerate(v):
                    if x[3] or x[4] < 1e9: continue
                    if not rules(v, k, R): continue
                    p = replay(v, x[0], x[1], off, hold)
                    if p is not None: vals.append((x[8], p))
            if not vals: continue
            vals.sort(); mid = vals[len(vals)//2][0]
            h1 = sum(p for t, p in vals if t < mid); h2 = sum(p for t, p in vals if t >= mid)
            print(f"{name:9s} landing +{off:3d} txs hold {hold} | trades {len(vals):5d} ({len(vals)/hours:4.0f}/h) | total {sum(p for _, p in vals):+7.2f} SOL ({sum(p for _, p in vals)/hours*24:+6.1f}/day) | per trade {sum(p for _, p in vals)/len(vals):+.4f} | halves {h1:+.2f} / {h2:+.2f} | reverts {sum(1 for _, p in vals if p == -0.0005)/len(vals):.0%}")
