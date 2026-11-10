# Per clock-hour series: market activity vs live P&L and shadow; then activity bins x early/late.
import json, collections, datetime, statistics as st
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
ME = 'EgxfYgEb'
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T = [t for t in T if not t['template']]
H = lambda ns: int(ns // 3.6e12)
hr = collections.defaultdict(lambda: collections.Counter()); pn = collections.defaultdict(list); fol = collections.defaultdict(list)
for l in open(D + 'market.jsonl'):
    d = json.loads(l)
    if d.get('t') is None: continue
    hr[H(d['t'])][d['ev']] += 1; hr[H(d['t'])]['run%d' % d['run']] += 1
sh = collections.defaultdict(list)
fillt = {}
nt = []
for l in open(D + 'market.jsonl'):
    d = json.loads(l)
    if d['ev'] == 'presend_fill' and d.get('t'): fillt[(d['run'], d['mint'], d['w'], d['row'], d['s_in'])] = d['t']
    elif d['ev'] == 'presend_exit': nt.append(d)
for d in nt:
    k = (d['run'], d['mint'], d['w'], d['row'], d['s_in'])
    if k in fillt and d['row'] in ('a', 'c'): sh[(H(fillt[k]), d['row'])].append(d['net_cheap'])
for t in T:
    pn[H(t['t'])].append(t['pnl'] / 1e6)
    tp = t['tape']; mine = [x for x in tp if x[0] == ME and x[1]]
    if mine:
        s1 = t['sell_slot'] or t['slot'] + 2
        fol[H(t['t'])].append(sum(x[2] for x in tp if x[0] != ME and x[1] and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s1) / 1e9)
rows = []
for h in sorted(hr):
    c = hr[h]
    if c['dump'] < 100: continue  # partial hours
    run = max((k for k in c if k.startswith('run')), key=lambda k: c[k])
    rows.append(dict(h=h, run=run, pkt=(datetime.datetime(1970, 1, 1) + datetime.timedelta(hours=h + 5)).strftime('%m-%d %H'),
                     dumps=c['dump'], trig=c['presend_arm'], arms=c['live_arm'], n=len(pn[h]), pnl=sum(pn[h]), avg=(sum(pn[h]) / len(pn[h]) if pn[h] else None),
                     fol=(st.mean(fol[h]) if fol[h] else None), sha=sum(sh[(h, 'a')]), shc=sum(sh[(h, 'c')]), nsha=len(sh[(h, 'a')]), nshc=len(sh[(h, 'c')])))
json.dump(rows, open(D + 'hourly.json', 'w'))
print('hour(PKT)  run   dumps trig arms  n   liveSOL avg_mSOL folSOL shA_SOL shC_SOL')
for r in rows:
    print('%s %5s %6d %4d %4d %3d %8.3f %8s %6s %7.3f %7.3f' % (r['pkt'], r['run'], r['dumps'], r['trig'], r['arms'], r['n'], r['pnl'] / 1e3,
          '%.1f' % r['avg'] if r['avg'] is not None else '-', '%.2f' % r['fol'] if r['fol'] is not None else '-', r['sha'], r['shc']))
# activity terciles x early/late
ds = sorted(r['dumps'] for r in rows); q1, q2 = ds[len(ds) // 3], ds[2 * len(ds) // 3]
print('\nterciles dumps/h cut', q1, q2)
LATE = lambda r: r['h'] >= H(1793570000e9) if False else None
cut = [t for t in T if t['run'] == 42]; cut.sort(key=lambda t: t['t']); cutH = H(cut[int(len(cut) * 2 / 5)]['t'])  # start of 42.3
print('late = from hour', cutH)
for name, f in (('early(r40..42.2)', lambda r: r['h'] < cutH), ('late(42.3..r46)', lambda r: r['h'] >= cutH)):
    for lo, hi, lab in ((0, q1, 'quiet'), (q1, q2, 'mid'), (q2, 1e9, 'busy')):
        rr = [r for r in rows if f(r) and lo <= r['dumps'] < hi]
        n = sum(r['n'] for r in rr); p = sum(r['pnl'] for r in rr)
        na = sum(r['nsha'] for r in rr); nc = sum(r['nshc'] for r in rr)
        print('%-17s %-5s hours %3d  live n %4d avg %6.1f mSOL  SOL/h %+.3f | shadowA %5.1f mSOL/fill  shadowC %5.1f mSOL/fill' % (
            name, lab, len(rr), n, p / n if n else 0, p / 1e3 / max(1, len(rr)), 1000 * sum(r['sha'] for r in rr) / max(1, na), 1000 * sum(r['shc'] for r in rr) / max(1, nc)))
