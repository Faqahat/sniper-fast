#!/usr/bin/env python3
# Matched comparison: restored dump (bait proxy) vs ordinary moments on the SAME kind of token (age, curve, recent
# activity, recent run-up). Then per-trade P&L of the bait vs (a) selling right away and (b) just holding.
import gzip, json, glob, collections, statistics as st, bisect
W = ['1', '2', '3', '4', '6']
FEE = 0.0125
def cell(r):
    b = lambda x, cuts: bisect.bisect(cuts, x)
    return (b(r['age'], [150, 600]), b(r['vsol'], [40, 55, 75]), b(r['n20'], [4, 11, 26, 50]),
            b(r['b20'], [0.5, 2, 5, 12]), b(r['r20'], [0.9, 1.0, 1.15, 1.4]))
rest = collections.defaultdict(list); base = collections.defaultdict(list); dump = []
for f in glob.glob('/home/moiz/sniper-data/strategies/baitflip2/*.jsonl.gz'):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l)
        if r['age'] < 15 or r['age'] > 2000 or not (28 <= r['vsol'] <= 100): continue
        if r['kind'] == 'rest' and r['sell'] >= 0.5 and 0.985 <= r['rr'] <= 1.02: rest[r['run']].append(r)
        elif r['kind'] == 'base': base[cell(r)].append(r)
bm = {c: {w: (st.mean(x['out'][w][6] for x in v), st.mean(x['out'][w][1] for x in v), st.mean(x['out'][w][3] for x in v)) for w in W}
      for c, v in base.items() if len(v) >= 30}
print("cells with base>=30:", len(bm))
for run in sorted(rest) + ['ALL']:
    rows = [r for k in rest for r in rest[k]] if run == 'ALL' else rest[run]
    rows = [r for r in rows if cell(r) in bm]
    print(f"\n== {run}: matched restored dumps n={len(rows)}")
    print(" w | rest px/p0  base px/p0  lift  | rest buySOL base buySOL | rest dipbots base dipbots")
    for w in W:
        rp = st.mean(r['out'][w][6] for r in rows); bp = st.mean(bm[cell(r)][w][0] for r in rows)
        rb = st.mean(r['out'][w][1] for r in rows); bb = st.mean(bm[cell(r)][w][1] for r in rows)
        rd = st.mean(r['out'][w][3] for r in rows); bd = st.mean(bm[cell(r)][w][2] for r in rows)
        print(f"{w:>2} |   {rp:.4f}     {bp:.4f}   {100*(rp-bp):+.2f}% |   {rb:.3f}      {rb-bb:+.3f} more |   {rd:.3f}  {rd-bd:+.3f} more")
# per-trade P&L of the bait, using each event's own sell size as X (bait size), exit at window w
rows = [r for k in rest for r in rest[k] if cell(r) in bm]
print("\n== P&L per bait (SOL). X = bait sell size of the event; costs = 2.5% of X + 0.0015 tx/tip")
print(" pos  w | vs SELL NOW: mean  median  win% | vs JUST HOLD: mean")
for P in [1, 2, 3, 5]:
    for w in ['2', '4']:
        g = [P * (r['out'][w][6] - 1) - 2 * FEE * r['sell'] - 0.0015 for r in rows]
        h = [P * (r['out'][w][6] - bm[cell(r)][w][0]) - 2 * FEE * r['sell'] - 0.0015 for r in rows]
        print(f"{P:>4} {w:>2} | {st.mean(g):+.4f} {st.median(g):+.4f} {100*sum(x>0 for x in g)/len(g):4.0f}% | {st.mean(h):+.4f}")
# X sized smallest that still triggers: 0.5 SOL bait only
small = [r for r in rows if r['sell'] < 0.7]
print(f"\n== bait 0.5-0.7 SOL only (n={len(small)})")
for P in [1, 2, 3, 5]:
    w = '4'
    g = [P * (r['out'][w][6] - 1) - 2 * FEE * r['sell'] - 0.0015 for r in small]
    h = [P * (r['out'][w][6] - bm[cell(r)][w][0]) - 2 * FEE * r['sell'] - 0.0015 for r in small]
    print(f" pos {P}: vs sell now {st.mean(g):+.4f} (median {st.median(g):+.4f}), vs hold {st.mean(h):+.4f}")
