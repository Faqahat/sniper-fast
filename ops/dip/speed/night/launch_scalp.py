#!/usr/bin/env python3
# Owner idea (10-25): hot new launch -> buy 2 / 3.2 SOL early -> sell into the buyers that come after. READ-ONLY, 7 h chain.
# Launch = token whose first SOL-curve trade is inside the window. TRIGGER = by age <= TRIG_S seconds the token has >= NB distinct buyers and
# >= SOL_IN SOL bought. Entry = the curve OFF txs after the trigger trade (our landing; next slot if the block ends), +GUARD guard.
# Our buy is inserted into the curve; exit = sell our tokens into the curve after K more distinct buyers or after T slots (whichever first),
# with our buy still inside the reserves. 1.25% pump fee per side, 0.0016 SOL tx+tips, gains cut CUT (followers priced out by a big buy).
import json, collections, bisect, statistics
rows = json.load(open("race_rows.json"))
T = collections.defaultdict(list)
for r in rows:
    if r[4]:
        for t in r[11]:
            if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6]))
s_lo = rows[0][0] + 300; hours = (rows[-1][0] - s_lo) * 0.2126 / 3600
FEE = 0.0125
def sim(SIZE, NB, SOL_IN, TRIG_S, K, TSL, OFF=80, GUARD=1.10, CUT=0.3):
    res = []
    for m, v in T.items():
        v.sort()
        if v[0][0] < s_lo: continue                                    # launched inside the window
        s0 = v[0][0]; buyers = set(); sol_in = 0; trig = None
        for k, x in enumerate(v):
            if (x[0] - s0) * 0.2126 > TRIG_S: break
            if x[3]: buyers.add(x[2]); sol_in += x[4]
            if len(buyers) >= NB and sol_in >= SOL_IN * 1e9: trig = k; break
        if trig is None: continue
        keys = [(x[0], x[1]) for x in v]; tx = v[trig]
        ke = bisect.bisect_left(keys, (tx[0], tx[1] + 1 + OFF)) - 1; ev = v[ke]
        if (ev[6] / ev[7]) / (tx[6] / tx[7]) > GUARD: res.append(-0.0005); continue
        xin = SIZE * 1e9 * (1 - FEE); q = ev[7] * xin / (ev[6] + xin)
        later = set(); exit_k = None
        for j in range(ke + 1, len(v)):
            y = v[j]
            if y[3]: later.add(y[2])
            if len(later) >= K or y[0] - ev[0] >= TSL: exit_k = j; break
        if exit_k is None: exit_k = len(v) - 1
        xv = v[exit_k]
        out = (xv[6] + xin) * q / xv[7] * (1 - FEE)
        p = (out - SIZE * 1e9) / 1e9 - 0.0016
        res.append(p * (1 - CUT) if p > 0 else p)
    return res
print(f"window {hours:.1f} h | launches in window: {sum(1 for v in T.values() if min(x[0] for x in v) >= s_lo)}")
for SIZE in (2.0, 3.2):
    for NB, SOL_IN, TRIG_S in ((5, 5, 5), (10, 10, 10), (15, 20, 15)):
        for K, TSL in ((5, 10), (10, 20), (20, 40)):
            r = sorted(res := sim(SIZE, NB, SOL_IN, TRIG_S, K, TSL))
            if not r: continue
            print(f"buy {SIZE} SOL | trigger {NB} buyers + {SOL_IN} SOL within {TRIG_S}s | exit after {K} more buyers or {TSL} slots | trades {len(r):4d} ({len(r)/hours:4.0f}/h) | total {sum(r):+7.2f} SOL ({sum(r)/hours*24:+6.1f}/day) | per trade {sum(r)/len(r):+.4f} | win {sum(1 for x in r if x>0)/len(r):.0%} | worst {r[0]:+.2f}")
