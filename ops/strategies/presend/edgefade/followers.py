# Who buys after our fill (inside our hold) and who sells into it, per period. Wallets = 8-char prefixes (tape keeps 8 chars).
import json, collections, sys
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
ME = 'EgxfYgEb'
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T = [t for t in T if not t['template']]; T.sort(key=lambda t: t['t'])
r42 = [t for t in T if t['run'] == 42]; cuts = [r42[int(len(r42) * i / 5)]['t'] for i in range(1, 5)]
def per(t):
    if t['run'] == 42: return '42.' + str(1 + sum(1 for c in cuts if t['t'] >= c))
    return {40: 'E', 41: 'E'}.get(t['run'], 'L')
G = {'E': 'early r40-42.2', 'L': 'late 42.3-46'}
def grp(t):
    p = per(t)
    return 'E' if p in ('E', '42.1', '42.2') else 'L'
buyN = collections.defaultdict(collections.Counter); buyS = collections.defaultdict(collections.Counter)
sellS = collections.defaultdict(collections.Counter); aheadN = collections.defaultdict(collections.Counter)
nT = collections.Counter(); pnlw = collections.defaultdict(lambda: collections.defaultdict(list))
for t in T:
    g = grp(t); nT[g] += 1
    tp = t['tape']; mine = [x for x in tp if x[0] == ME and x[1]]
    if not mine: continue
    s1 = t['sell_slot'] or t['slot'] + 2
    seen = set()
    for x in tp:
        if x[0] == ME or (x[3], x[4]) <= (mine[0][3], mine[0][4]) or x[3] > s1: continue
        if x[1]: buyN[g][x[0]] += 1; buyS[g][x[0]] += x[2] / 1e9; seen.add(x[0])
        else: sellS[g][x[0]] += x[2] / 1e9
    for u in seen: pnlw[u][g].append(t['pnl'] / 1e6)
    for x in t.get('between', []):
        if x[1] and x[0] != ME: aheadN[g][x[0]] += 1
def rate(c, g, u): return c[g][u] / nT[g]
print('trades', dict(nT))
for g in ('E', 'L'):
    print('distinct follower wallets %s: %d ; follower SOL/trade %.2f ; top-10 share of follower SOL %.0f%%' % (
        G[g], len(buyS[g]), sum(buyS[g].values()) / nT[g], 100 * sum(v for _, v in buyS[g].most_common(10)) / sum(buyS[g].values())))
print('\nTop followers by SOL bought inside our hold (per 100 trades): early vs late')
top = set(u for u, _ in buyS['E'].most_common(20)) | set(u for u, _ in buyS['L'].most_common(20))
print('wallet    E_buys E_SOL  L_buys L_SOL   E_avg_pnl_when_present L_avg')
for u in sorted(top, key=lambda u: -(buyS['E'][u] / nT['E'] + buyS['L'][u] / nT['L'])):
    pe = pnlw[u]['E']; pl = pnlw[u]['L']
    print('%-9s %6.1f %5.1f  %6.1f %5.1f   %6.1f (%d)  %6.1f (%d)' % (u, 100 * rate(buyN, 'E', u), 100 * rate(buyS, 'E', u), 100 * rate(buyN, 'L', u), 100 * rate(buyS, 'L', u),
          sum(pe) / len(pe) if pe else 0, len(pe), sum(pl) / len(pl) if pl else 0, len(pl)))
print('\nTop sellers inside our hold (SOL per 100 trades)')
top = set(u for u, _ in sellS['E'].most_common(12)) | set(u for u, _ in sellS['L'].most_common(12))
for u in sorted(top, key=lambda u: -(sellS['L'][u] / nT['L'])):
    print('%-9s E %6.1f  L %6.1f' % (u, 100 * sellS['E'][u] / nT['E'], 100 * sellS['L'][u] / nT['L']))
print('\nTop buyers AHEAD of us (count per 100 trades)')
top = set(u for u, _ in aheadN['E'].most_common(10)) | set(u for u, _ in aheadN['L'].most_common(10))
for u in sorted(top, key=lambda u: -(aheadN['L'][u] / nT['L'])):
    print('%-9s E %5.1f  L %5.1f' % (u, 100 * aheadN['E'][u] / nT['E'], 100 * aheadN['L'][u] / nT['L']))
