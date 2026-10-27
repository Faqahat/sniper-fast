#!/usr/bin/env python3
# Compare price/flow after: restored dumps (bait proxy) vs plain dumps vs ordinary moments (hold, no bait).
import gzip, json, glob, collections, statistics as st, sys
R = collections.defaultdict(list)
for f in glob.glob('/home/moiz/sniper-data/strategies/baitflip2/*.jsonl.gz'):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l)
        if r['age'] < 15 or r['age'] > 2000: continue       # skip launch-bundle phase and very old tokens
        if not (28 <= r['vsol'] <= 100): continue
        if r['kind'] == 'rest':
            if r['sell'] >= 0.5 and 0.985 <= r['rr'] <= 1.02: R['rest_full'].append(r)
            elif r['sell'] >= 0.5: R['rest_part'].append(r)
        elif r['kind'] == 'dump':
            if r['sell'] >= 0.5: R['dump'].append(r)
        else: R['base'].append(r)
W = ['0', '1', '2', '3', '4', '6', '8']
def summ(rows, name):
    print(f"\n== {name}  n={len(rows)}")
    print(" w  buys/ev  buySOL  dipbots  sellSOL  px_last/p0 (mean, median)  px_max/p0  P(px_last>1.02)")
    for w in W:
        o = [r['out'][w] for r in rows]
        pl = [x[6] for x in o]; pm = [x[7] for x in o]
        print(f"{w:>2}  {st.mean(x[0] for x in o):6.2f}  {st.mean(x[1] for x in o):6.3f}  {st.mean(x[3] for x in o):6.3f}  {st.mean(x[5] for x in o):6.3f}   {st.mean(pl):.4f} {st.median(pl):.4f}   {st.mean(pm):.4f}   {sum(p>1.02 for p in pl)/len(pl):.3f}")
for k in ['rest_full', 'rest_part', 'dump', 'base']: summ(R[k], k)
# rest_full split by restorer being a known dip bot, by sell size
for lab, f in [('rest_full restorer=dipbot', lambda r: r['rdip']), ('rest_full restorer=other', lambda r: not r['rdip']),
               ('rest_full sell>=1', lambda r: r['sell'] >= 1), ('rest_full sell 0.5-1', lambda r: r['sell'] < 1),
               ('rest_full by run R1', lambda r: r['run']=='R1'), ('rest_full by run R2', lambda r: r['run']=='R2'), ('rest_full by run R3', lambda r: r['run']=='R3')]:
    summ([r for r in R['rest_full'] if f(r)], lab)
