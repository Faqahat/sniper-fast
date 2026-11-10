# Timeline of key follower wallets per period (live holds) + market-wide presence in all attempt windows; pnl vs follower SOL.
import json, collections
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
ME = 'EgxfYgEb'
W = ['2VggYpPu', 'HLU8QbLd', 'DSvgfynk', 'DF7eRXHn', 'CvHEVC7S', '6VzXcLk9', 'haqq6qnV', '4ggJqUDD', '3qvuM3U5', '8yYMhuYo']
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T = [t for t in T if not t['template']]; T.sort(key=lambda t: t['t'])
r42 = [t for t in T if t['run'] == 42]; cuts = [r42[int(len(r42) * i / 5)]['t'] for i in range(1, 5)]
def per(run, t):
    if run == 42: return '42.' + str(1 + sum(1 for c in cuts if t >= c))
    return '45+46' if run in (45, 46) else str(run)
ORDER = ['40', '41', '42.1', '42.2', '42.3', '42.4', '42.5', '43', '44', '45+46']
fb = collections.defaultdict(collections.Counter); fs = collections.defaultdict(collections.Counter); n = collections.Counter()
X = []
for t in T:
    P = per(t['run'], t['t']); n[P] += 1
    tp = t['tape']; mine = [x for x in tp if x[0] == ME and x[1]]
    if not mine: continue
    s1 = t['sell_slot'] or t['slot'] + 2
    vs = mine[0][5] / 1e9
    tot = 0
    for x in tp:
        if x[0] == ME or (x[3], x[4]) <= (mine[0][3], mine[0][4]) or x[3] > s1: continue
        if x[1]: fb[P][x[0]] += x[2] / 1e9; tot += x[2] / 1e9
        else: fs[P][x[0]] += x[2] / 1e9
    X.append((P, tot, sum(1 for x in tp if x[0] != ME and not x[1] and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s1 for _ in [0]) , t['pnl'] / 1e6, vs, t['sol_in'] / 1e9))
print('Follower BUY SOL inside our hold, per 100 trades')
print('wallet   ' + ''.join(p.rjust(7) for p in ORDER))
for w in W:
    print('%-9s' % w + ''.join(('%7.1f' % (100 * fb[p][w] / n[p])) for p in ORDER))
print('4ggJ sell' + ''.join(('%7.1f' % (100 * fs[p]['4ggJqUDD'] / n[p])) for p in ORDER))
# market-wide presence of these wallets in ALL attempt windows (between+after lists), per hour of window, by period
pres = collections.defaultdict(collections.Counter); nwin = collections.Counter()
with open(D + 'r42_dummy', 'w') as _: pass
for r in (40, 41, 42, 43, 44, 45, 46):
    last = None
    for l in open(D + 'ex/r%d.jsonl' % r):
        if '"presend_attempt_land"' not in l: continue
        d = json.loads(l)
        key = (d['mint'], d['d'].get('slot'))
        if key == last: continue   # one count per dump window (first attempt record)
        last = key
        P = per(r, d['t'] or d['t_send']); nwin[P] += 1
        us = set(x[0] for x in d['between'] + d['after'] if x[1])
        for w in W:
            if w in us: pres[P][w] += 1
print('\nMarket-wide: share of our attempt windows (dump windows we fired at) where the wallet BUYS right after the dump, %')
print('windows  ' + ''.join(('%7d' % nwin[p]) for p in ORDER))
for w in W:
    print('%-9s' % w + ''.join(('%7.1f' % (100 * pres[p][w] / max(1, nwin[p]))) for p in ORDER))
# pnl vs follower SOL
import statistics as st
print('\nLive pnl by follower-SOL bucket (all periods, non-template)')
for lo, hi in ((0, 0.01), (0.01, 1), (1, 2), (2, 4), (4, 1e9)):
    xs = [x for x in X if lo <= x[1] < hi]
    print('fol %4.2f..%-5g n %4d avg pnl %6.1f mSOL' % (lo, hi, len(xs), sum(x[3] for x in xs) / len(xs)))
# within-bucket pnl early vs late (does the same follower flow pay less late?)
print('\nSame follower bucket, early vs late avg pnl mSOL')
E = lambda p: p in ('40', '41', '42.1', '42.2')
for lo, hi in ((0, 0.01), (0.01, 1), (1, 2), (2, 4), (4, 1e9)):
    e = [x[3] for x in X if lo <= x[1] < hi and E(x[0])]; l_ = [x[3] for x in X if lo <= x[1] < hi and not E(x[0])]
    print('fol %4.2f..%-5g early n %4d %6.1f | late n %4d %6.1f' % (lo, hi, len(e), sum(e) / len(e), len(l_), sum(l_) / len(l_)))
