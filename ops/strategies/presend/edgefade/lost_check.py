# Early trades split by whether any of the vanished followers bought inside our hold; compare with late.
import json
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
ME = 'EgxfYgEb'; LOST = {'2VggYpPu', 'HLU8QbLd', 'DSvgfynk', 'DF7eRXHn', 'CvHEVC7S', '6VzXcLk9'}; NEW = {'haqq6qnV'}
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T = [t for t in T if not t['template']]; T.sort(key=lambda t: t['t'])
r42 = [t for t in T if t['run'] == 42]; cut = r42[int(len(r42) * 2 / 5)]['t']
def has(t, S):
    tp = t['tape']; mine = [x for x in tp if x[0] == ME and x[1]]
    if not mine: return False
    s1 = t['sell_slot'] or t['slot'] + 2
    return any(x[0] in S and x[1] and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s1 for x in tp)
pct = lambda xs: sum(100 * t['pnl'] / t['sol_in'] for t in xs) / max(1, len(xs))
E = [t for t in T if t['t'] < cut]; L = [t for t in T if t['t'] >= cut]
a = [t for t in E if has(t, LOST)]; b = [t for t in E if not has(t, LOST)]
print('early all     n %4d  pnl %%size %+.2f' % (len(E), pct(E)))
print('early w/ lost n %4d (%.0f%%) pnl %%size %+.2f' % (len(a), 100 * len(a) / len(E), pct(a)))
print('early w/o lost n %4d       pnl %%size %+.2f' % (len(b), pct(b)))
c = [t for t in L if has(t, NEW)]; d = [t for t in L if not has(t, NEW)]
print('late all      n %4d  pnl %%size %+.2f' % (len(L), pct(L)))
print('late w/ haqq6qnV n %4d (%.0f%%) pnl %%size %+.2f ; w/o n %d %+.2f' % (len(c), 100 * len(c) / len(L), pct(c), len(d), pct(d)))
print('early contribution of lost-follower trades: %.2f %%size per early trade' % (pct(E) - pct(b) * len(b) / len(E) - 0))
