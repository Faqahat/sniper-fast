# First/last time key wallets buy in any of our attempt windows; net flow by others inside our hold per bucket.
import json, datetime, collections
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
W = ['2VggYpPu', 'HLU8QbLd', 'DSvgfynk', 'DF7eRXHn', 'CvHEVC7S', '6VzXcLk9', 'haqq6qnV', '3qvuM3U5']
first = {}; last = {}
pkt = lambda ns: (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ns / 1e9, hours=5)).strftime('%m-%d %H:%M')
for r in (40, 41, 42, 43, 44, 45, 46):
    for l in open(D + 'ex/r%d.jsonl' % r):
        if '"presend_attempt_land"' not in l: continue
        d = json.loads(l)
        for x in d['between'] + d['after']:
            if x[0] in W and x[1] and x[5]:
                first.setdefault(x[0], x[5]); last[x[0]] = x[5]
for w in W: print('%-9s first %s  last %s' % (w, pkt(first[w]) if w in first else '-', pkt(last[w]) if w in last else '-'))
ME = 'EgxfYgEb'
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T = [t for t in T if not t['template']]; T.sort(key=lambda t: t['t'])
r42 = [t for t in T if t['run'] == 42]; cut = r42[int(len(r42) * 2 / 5)]['t']
print('early/late cut (start of 42.3):', pkt(cut))
agg = collections.defaultdict(list)
for t in T:
    tp = t['tape']; mine = [x for x in tp if x[0] == ME and x[1]]
    if not mine: continue
    s1 = t['sell_slot'] or t['slot'] + 2
    o = [x for x in tp if x[0] != ME and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s1]
    b = sum(x[2] for x in o if x[1]) / 1e9; s = sum(x[2] for x in o if not x[1]) / 1e9
    bk = 0 if b < 0.01 else 1 if b < 1 else 2 if b < 2 else 3 if b < 4 else 4
    agg[(t['t'] >= cut, bk)].append((s, t['pnl'] / 1e6, t['sat'], t.get('ms_after_d')))
print('bucket  early: sells-in-hold SOL, pnl | late: sells SOL, pnl')
for bk in range(5):
    e = agg[(False, bk)]; l_ = agg[(True, bk)]
    m = lambda xs, i: sum(x[i] for x in xs if x[i] is not None) / max(1, len(xs))
    print(bk, ' %5.2f %6.1f (%d) | %5.2f %6.1f (%d)' % (m(e, 0), m(e, 1), len(e), m(l_, 0), m(l_, 1), len(l_)))
