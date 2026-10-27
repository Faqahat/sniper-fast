#!/usr/bin/env python3
# DF7eRXHn study: decode his buy args (own program 41Pr4X: [SOL in u64][min tokens out u64][flag u8]) on the RPC sample and
# compare min-out with the tokens the curve would give at (a) the state right before his buy, (b) the trigger trade's state.
import json, gzip, bisect, collections, sys, statistics as st
sys.path.insert(0, '/home/moiz/sniper/ops/dip/speed/landing2'); sys.path.insert(0, '/home/moiz/sniper/ops/dip/speed/landing2/df7e')
from rpc_ro import get_tx
from d2_tx import dec
D = '/home/moiz/sniper-data/landing2/df7e'
R = {x['sig']: x for x in json.load(open(f'{D}/buys2.json'))}
sigs = [l.split()[1] for l in open(sys.argv[1])]
sigs = [s for s in sigs if s in R]
mints = {R[s]['mint'] for s in sigs}
TR = collections.defaultdict(list)
for l in gzip.open(f'{D}/T_mints.jsonl.gz', 'rt'):
    r = json.loads(l)
    if r[5] in mints: TR[r[5]].append(r)
for m in TR: TR[m] = sorted({(r[2], r[6]): r for r in TR[m]}.values(), key=lambda r: (r[0], r[1]))
out = []
for s in sigs:
    t = get_tx(s); m = t['transaction']['message']; keys = m['accountKeys']
    ix = [i for i in m['instructions'] if keys[i['programIdIndex']].startswith('41Pr4X')]
    if not ix: continue
    d = dec(ix[0]['data']); a = int.from_bytes(d[0:8], 'little'); b = int.from_bytes(d[8:16], 'little')
    x = R[s]; v = TR[x['mint']]; ks = [(r[0], r[1]) for r in v]; j = bisect.bisect_left(ks, (x['s'], x['i']))
    p = v[j - 1]; net = a * (1 - 0.0047)
    exp = p[9] - p[8] * p[9] / (p[8] + net)
    expT = None
    if x.get('trig_sig'):
        q = [r for r in v if r[2] == x['trig_sig']]
        if q: q = q[0]; expT = q[9] - q[8] * q[9] / (q[8] + net)
    out.append(dict(ok=x['ok'], sol=a, minout=b, tol_now=1 - b / exp, tol_trig=(1 - b / expT) if expT else None, trig=x['trig']))
for o in out[:8]: print(o)
for k in ('tol_now', 'tol_trig'):
    for okf in (True, False):
        v = sorted(o[k] for o in out if o[k] is not None and o['ok'] == okf)
        if v: print(k, 'ok' if okf else 'failed', len(v), 'p10/25/50/75/90', [round(v[int(p * (len(v) - 1))], 3) for p in (.1, .25, .5, .75, .9)])
# reference = curve state BEFORE the trigger trade (pre-dump price for dump backruns, pre-buy price for buy triggers)
print("\nmin-out vs tokens at the state BEFORE the trigger trade (1 - ratio; >0 = he accepts a worse price than pre-trigger)")
G = collections.defaultdict(list)
for s in sigs:
    x = R[s]
    if not x.get('trig_sig'): continue
    v = TR[x['mint']]; q = [r for r in v if r[2] == x['trig_sig']]
    if not q: continue
    q = q[0]; k = q[8] * q[9]
    vs_b = q[8] + q[7] if q[6] == 0 else q[8] - q[7]; vt_b = k / vs_b
    t = get_tx(s); m = t['transaction']['message']; keys = m['accountKeys']
    ix = [i for i in m['instructions'] if keys[i['programIdIndex']].startswith('41Pr4X')][0]
    d = dec(ix['data']); a = int.from_bytes(d[0:8], 'little'); b = int.from_bytes(d[8:16], 'little')
    net = a * (1 - 0.0047); exp_b = vt_b - vs_b * vt_b / (vs_b + net)
    G[x['trig']].append((round(1 - b / exp_b, 3), x['ok']))
for g, v in G.items(): print(g, sorted(v))
