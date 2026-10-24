#!/usr/bin/env python3
# Our strategy on the owner's token list (local only): every >=1 SOL dump on those tokens (sel3r = real follower limits), frozen
# IMIT1 tiers with their TP/SL/time-limit exits, entry 35/50/75 ms, 2% price guard, spacing 5 slots. Split: dumps before
# 10-23 06:00 PKT were in the model's TRAINING data (not a fair test); after = unseen. Also: buying EVERY dump (no selection),
# the three wallets' picks on the same tokens, and per-token lines.
import sys, json, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
M = json.load(open("/home/moiz/sniper/ops/overnight/sel/IMIT1.json")); sc = np.load("/home/moiz/sniper/ops/overnight/sel/x4_score_imit1_3r.npy")
LST = set(l.strip() for l in open("/home/moiz/sniper/ops/overnight/sel/owner_list/mints.txt") if l.strip())
inl = np.array([m in LST for m in S.M])
G = {tuple(g): i for i, g in enumerate(S.GRID)}
print(f"dumps on the listed tokens: {int(inl.sum())} (before 06:00 PKT {int((inl & S.TR).sum())}, after {int((inl & S.TE).sum())}); tokens with >= 1 dump: {len(set(S.M[inl]))} of {len(LST)}")
def block(name, pick, e):
    for part, nm in ((S.TR, "in TRAINING hours (<06:00, not fair)"), (S.TE, "UNSEEN hours (>=06:00)       ")):
        m = pick & inl & part; seg = []
        for L in S.LATS:
            j = S.LATS.index(L); p = S.pnl(L, e); fl = m & S.FILL[:, j] & S.HAS[:, j]
            seg.append(f"{L} ms {p[m].sum():+6.2f} (fills {int(fl.sum())}, win {((p[fl] > 0).mean() if fl.any() else 0):.0%})")
        print(f"  {name:34s} {nm} picks {int(m.sum()):4d} on {len(set(S.M[m])):3d} tokens | " + " | ".join(seg))
for tier in ("top2", "top4", "top8"):
    block(f"IMIT1 {tier} ({S.ename(G[tuple(M['exits'][tier])])[:22]})", S.spaced(sc >= M["thresholds"][tier]), G[tuple(M["exits"][tier])])
block("every dump (no selection), same exit", S.spaced(np.ones(len(S.EV), bool)), G[tuple(M["exits"]["top4"])])
block("the 3 wallets' own picks, same exit", S.LAB["ANY"], G[tuple(M["exits"]["top4"])])
# per token (top4, unseen hours + training hours marked)
e = G[tuple(M["exits"]["top4"])]; pick = S.spaced(sc >= M["thresholds"]["top4"]) & inl; p35 = S.pnl(35, e)
rows = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0, 0.0])
for i in np.where(inl)[0]:
    r = rows[S.M[i]]; r[2] += 1; r[4] += int(S.LAB["ANY"][i])
    if pick[i]: r[0] += 1; r[1] += p35[i]; r[3] += int(S.FILL[i, 0] and p35[i] > 0)
    r[5] = max(r[5], S.EV[i]["tok"]["vmax"])
traded = sorted(((m, v) for m, v in rows.items() if v[0]), key=lambda x: -x[1][1])
print(f"\nper token, IMIT1 top4 at 35 ms: traded {len(traded)} of {len(rows)} tokens with dumps; net positive {sum(1 for m, v in traded if v[1] > 0)}")
for m, v in traded[:8] + [("...", None)] + traded[-5:]:
    if v is None: print("   ..."); continue
    print(f"   {m[:8]} picks {v[0]:2d} wins {v[3]:2d} P&L {v[1]:+.3f} | dumps on token {v[2]:3d}, the 3 bought {v[4]:3d} | max curve {v[5]:.0f} SOL")
