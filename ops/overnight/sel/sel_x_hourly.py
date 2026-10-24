#!/usr/bin/env python3
# Hour by hour (PKT) on TEST hours, side by side with the three wallets: a pick mask (GBDT score >= THR, or rules JSON) with a
# TP/SL/time-limit exit. Per hour: all dumps / tokens, THEIR dumps / tokens, OUR picks / tokens, overlap, fills, win%, P&L at
# 35/50/75 ms; tokens: how many of OUR filled tokens ended net positive. Also the hold-time spread of our trades (per exit kind).
# usage: python3 -I sel_x_hourly.py score.npy THR EXIT_INDEX   |   python3 -I sel_x_hourly.py rules.json - EXIT_INDEX
import sys, os, json, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
src, thr, e = sys.argv[1], sys.argv[2], int(sys.argv[3])
if src.endswith(".mask.npy"): sel = np.load(src).astype(bool)
elif src.endswith(".npy"): sel = np.load(src) >= float(thr)
else:
    rules = json.load(open(src)); rules = rules if rules and isinstance(rules[0][0], list) else [rules]
    sel = np.zeros(len(S.EV), bool)
    for c in rules:
        m = np.ones(len(S.EV), bool)
        for k, op, v in c:
            j = S.FEATS.index(k); m &= (S.X[:, j] >= v) if op == ">=" else (S.X[:, j] <= v)
        sel |= m
pick = S.spaced(sel) & S.TE
P = {L: S.pnl(L, e) for L in S.LATS}
hr = np.array([time.strftime("%m-%d %H", time.gmtime(t + 18000)) for t in S.T])
print(f"exit: {S.ename(e)} | TEST from {time.strftime('%m-%d %H:%M', time.gmtime(S.T[S.TE].min() + 18000))} PKT")
print("hour PKT | dumps tokens | THEIR dumps tokens (% of dumps) | OUR picks tokens (% of dumps) | ours also theirs | 35 ms fills win P&L | 50 ms win P&L | 75 ms win P&L")
tot = collections.Counter(); TOKP = collections.defaultdict(float); nh = 0
for h in sorted(set(hr[S.TE])):
    m = S.TE & (hr == h); o = pick & m; th = S.LAB["ANY"] & m; nh += 1
    row = dict(d=m.sum(), dt=len(set(S.M[m])), t=th.sum(), tt=len(set(S.M[th])), o=o.sum(), ot=len(set(S.M[o])), both=(o & S.LAB["ANY"]).sum())
    seg = []
    for j, L in enumerate(S.LATS):
        fl = o & S.FILL[:, j] & S.HAS[:, j]; w = (P[L][fl] > 0).sum(); p = P[L][o].sum()
        row[f"f{L}"] = fl.sum(); row[f"w{L}"] = w; row[f"p{L}"] = p; seg.append(f"{fl.sum():3d} {w / max(fl.sum(), 1):4.0%} {p:+6.2f}")
    for k, v in row.items(): tot[k] += v
    print(f"{h}    | {row['d']:5d} {row['dt']:4d} | {row['t']:4d} {row['tt']:4d} ({row['t'] / row['d']:5.1%}) | {row['o']:4d} {row['ot']:4d} ({row['o'] / row['d']:5.1%}) | "
          f"{row['both'] / max(row['o'], 1):5.0%} | " + " | ".join(seg))
for i in np.where(pick & S.FILL[:, 0] & S.HAS[:, 0])[0]: TOKP[S.M[i]] += P[35][i]
print(f"TOTAL {nh} h: dumps {tot['d'] / nh:.0f}/h, tokens {tot['dt'] / nh:.0f}/h | THEIR {tot['t'] / nh:.1f} dumps/h ({tot['t'] / tot['d']:.1%}), {tot['tt'] / nh:.1f} tokens/h | "
      f"OUR {tot['o'] / nh:.1f} picks/h ({tot['o'] / tot['d']:.2%}), {tot['ot'] / nh:.1f} tokens/h | ours also theirs {tot['both'] / max(tot['o'], 1):.0%}")
for L in S.LATS:
    print(f"   {L} ms: fills {tot[f'f{L}']} ({tot[f'f{L}'] / nh:.1f}/h), win {tot[f'w{L}'] / max(tot[f'f{L}'], 1):.0%}, P&L {tot[f'p{L}']:+.2f} over {nh} h = {tot[f'p{L}'] / nh * 24:+.1f} SOL/day")
pos = sum(1 for v in TOKP.values() if v > 0)
print(f"   tokens we got filled on (35 ms): {len(TOKP)}, net positive {pos} ({pos / max(len(TOKP), 1):.0%})")
