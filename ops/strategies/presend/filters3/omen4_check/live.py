import json, pickle, sys, collections
OUT = "/home/moiz/sniper-data/filters3/omen4_check/live.pkl"
rows = []
for r in pickle.load(open('/home/moiz/sniper-data/levers/rows.pkl','rb')):
    rows.append(dict(run=f"r{r['run']}", t=r['t']/1e9, mint=r['mint'], slot=r['fill_slot'], kind=r['kind'], pnl=r['pnl'], size=r['size']))
def parse(fn, run):
    fills = []; real = collections.defaultdict(list)
    for l in open(fn):
        if '"presend_live_fill"' in l:
            d = json.loads(l); fills.append(d)
        elif '"presend_live_realized"' in l:
            d = json.loads(l); real[d['mint']].append(d['pnl'])
    out = []; used = collections.Counter()
    for d in fills:
        m = d['mint']; k = used[m]; used[m] += 1
        p = real[m][k] / 1e9 if k < len(real[m]) else None
        out.append(dict(run=run, t=d['t']/1e9, mint=m, slot=d['slot'], kind=d.get('kind', '?'), pnl=p, size=d['sol_in']/1e9))
    return out
have = {r['run'] for r in rows}
add = parse('/home/moiz/sniper-data/runs/ams/runs/dip_ams_r48.jsonl', 'r48') + parse('/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/r48/r49b.jsonl', 'r49')
rows += add
pickle.dump(rows, open(OUT, 'wb'))
import datetime as dt
pk = lambda t: (dt.datetime.utcfromtimestamp(t)+dt.timedelta(hours=5)).strftime('%m-%d %H:%M')
by = collections.defaultdict(list)
for r in rows: by[r['run']].append(r)
for k, v in sorted(by.items()):
    p = [x['pnl'] for x in v if x['pnl'] is not None]
    print(k, len(v), 'realized', len(p), f"{sum(p):+.3f}", pk(min(x['t'] for x in v)), '->', pk(max(x['t'] for x in v)), 'size', round(sorted(x['size'] for x in v)[len(v)//2],3), collections.Counter(x['kind'] for x in v))
