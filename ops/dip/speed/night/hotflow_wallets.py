#!/usr/bin/env python3
# Wallets trading like HOT1 (7 h chain, READ-ONLY): a BUY at a "hot flow" moment (>= 10 SOL bought on the token in the previous
# 15 s and >= 10 distinct buyers in the previous 5 s; slot = 212.6 ms) followed by the same wallet's SELL of that token within 5 s.
# Per wallet: such round trips, median hold, P&L from the trade events (SOL out - SOL in), win rate, trips per hour.
import json, collections, statistics, bisect
rows = json.load(open("race_rows.json"))
T = collections.defaultdict(list)    # mint -> [(slot, idx, user, buy, sol)]
for r in rows:
    if not r[4]: continue
    for t in r[11]:
        if 25_000_000_000 <= t[5] <= 200_000_000_000: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2]))   # SOL-quoted curves only (vsol 25-200 SOL)
s_lo, s_hi = rows[0][0], rows[-1][0]; hours = (s_hi - s_lo) * 0.2126 / 3600
W = collections.defaultdict(list)
for m, v in T.items():
    v.sort()
    slots = [x[0] for x in v]
    # each wallet's next sell after a buy
    for k, (s, i, u, buy, sol, tok) in enumerate(v):
        if not buy: continue
        a = bisect.bisect_left(slots, s - 70); b5 = bisect.bisect_left(slots, s - 24)
        flow = sum(x[4] for x in v[a:k] if x[3]) / 1e9
        buyers = len({x[2] for x in v[b5:k] if x[3]})
        if flow < 10 or buyers < 10: continue
        # same wallet's sell within 5 s (24 slots)
        for x in v[k + 1:]:
            if x[0] > s + 24: break
            if x[2] == u and not x[3]:
                if tok <= 0 or x[5] <= 0 or sol < 10_000_000: break        # skip dust buys (< 0.01 SOL)
                frac = min(1.0, tok / x[5])                                 # only the tokens THIS buy got
                W[u].append(((x[0] - s) * 0.2126, x[4] * frac / 1e9 - sol / 1e9 * (frac * x[5] / tok if tok else 1), sol / 1e9)); break
out = []
for u, v in W.items():
    if len(v) < 10: continue
    pnl = sum(p for _, p, _ in v)
    out.append((pnl, u, len(v), statistics.median([h for h, _, _ in v]), sum(1 for _, p, _ in v if p > 0) / len(v), statistics.median([s for *_, s in v])))
out.sort(reverse=True)
print(f"window {hours:.1f} h | wallets with >= 10 hot-flow round trips (sell <= 5 s): {len(out)}")
print("P&L SOL (trade events, before tx fees/tips) | wallet | trips | trips/h | median hold s | win | median size SOL")
for pnl, u, n, h, w, sz in out[:25]:
    print(f"  {pnl:+8.2f} | {u} | {n:4d} | {n/hours:5.1f} | {h:4.1f} | {w:4.0%} | {sz:.2f}")
json.dump([dict(pnl=p, wallet=u, trips=n, hold=h, win=w, size=sz) for p, u, n, h, w, sz in out], open("hotflow_wallets.json", "w"))
