#!/usr/bin/env python3
"""QUIET3 step 3: market-wide and per-token follower features from the observatory's backrun_sell records (s2_obs.py output), for
every live position (trades.jsonl) and every shadow T2 trigger (shadow.jsonl). Only records whose follower window had closed at the
decision time are used: sell t <= T - LAG (LAG = 15 s: the buyers need 2 slots, the 0.75-SOL value path v_sell needs 31 slots).
T = the trigger's time (arm time; rearm: the dump's time).
usage: s3_feat.py BRDIR OUTDIR"""
import sys, json, bisect, collections
BR, OUT = sys.argv[1], sys.argv[2]
LAG = 15 * 10**9
MIN = 60 * 10**9
recs = {}
for r in (37, 38, 39, 40, 41, 42):
    for l in open(f'{BR}/br{r}.jsonl'):
        d = json.loads(l); recs[(d['s'], d['i'])] = d
R = sorted(recs.values(), key=lambda d: d['t'])
TS = [d['t'] for d in R]
print('backrun records', len(R), flush=True)
# prefix sums: n, with-buyer, buyers, v_sell[+2 slots] (value after pump fee / 0.75), dump-like (drop >= 8%) n and with-buyer
def v2(d):
    v = d.get('vs') or []
    return v[1] if len(v) > 1 and v[1] is not None else None
P = collections.defaultdict(lambda: [0.0])
for d in R:
    dump = (d.get('drop') or 0) >= 8.0
    vals = {'n': 1, 'wb': 1 if d['nb'] > 0 else 0, 'nb': d['nb'], 'vn': 1 if v2(d) is not None else 0, 'v': v2(d) or 0.0,
            'dn': 1 if dump else 0, 'dwb': 1 if dump and d['nb'] > 0 else 0, 'dnb': d['nb'] if dump else 0,
            'dvn': 1 if dump and v2(d) is not None else 0, 'dv': (v2(d) or 0.0) if dump else 0.0}
    for k, x in vals.items(): P[k].append(P[k][-1] + x)
# active backrunner wallets: bought within 2 slots after >= 3 distinct big sells in the last 60 minutes (rolling, per minute)
t0 = TS[0] // MIN; t1 = TS[-1] // MIN + 1
bucket = collections.defaultdict(collections.Counter)
for d in R:
    for w in {x[0] for x in d['b']}: bucket[d['t'] // MIN][w] += 1
active = {}          # minute m -> set of wallets active over minutes [m-60, m)  (complete minutes before m)
roll = collections.Counter()
for m in range(t0, t1 + 1):
    active[m] = frozenset(w for w, c in roll.items() if c >= 3)
    roll.update(bucket.get(m, {}))
    old = bucket.get(m - 59)
    if old is not None and m - 59 >= t0:
        roll.subtract(old)
        for w in [w for w, c in roll.items() if c <= 0]: del roll[w]
# per token: its records in time order
TOK = collections.defaultdict(list)
for d in R: TOK[d['m']].append(d)

def feats(T, mint):
    hi = bisect.bisect_right(TS, T - LAG)
    f = {}
    cover = hi > 0 and TS[hi - 1] > T - LAG - 10 * MIN        # a record in the 10 min before: the observatory was on
    f['mk_cover'] = cover
    for M in (1, 5, 15, 60):
        lo = bisect.bisect_left(TS, T - LAG - M * MIN)
        g = lambda k: P[k][hi] - P[k][lo]
        n, dn = g('n'), g('dn')
        f[f'mk_n{M}'] = n if cover else None
        f[f'mk_wb{M}'] = (g('wb') / n if n else None) if cover else None
        f[f'mk_nb{M}'] = (g('nb') / n if n else None) if cover else None
        f[f'mk_v{M}'] = (g('v') / g('vn') if g('vn') else None) if cover else None
        f[f'mk_dwb{M}'] = (g('dwb') / dn if dn else None) if cover else None
        f[f'mk_dnb{M}'] = (g('dnb') / dn if dn else None) if cover else None
        f[f'mk_dv{M}'] = (g('dv') / g('dvn') if g('dvn') else None) if cover else None
    act = active.get((T - LAG) // MIN, frozenset())
    f['mk_bots60'] = len(act) if cover else None
    # this token's earlier big sells (closed)
    tk = [d for d in TOK.get(mint, []) if d['t'] <= T - LAG]
    f['tk_n'] = len(tk) if cover else None
    f['tk_nb'] = (sum(d['nb'] for d in tk) / len(tk) if tk else None) if cover else None
    f['tk_wb'] = (sum(d['nb'] > 0 for d in tk) / len(tk) if tk else None) if cover else None
    ws = set(); [ws.update(x[0] for x in d['b']) for d in tk]
    f['tk_buyers'] = len(ws) if cover else None
    f['tk_actbots'] = len(ws & act) if cover else None
    f['tk_v'] = (sum(v2(d) for d in tk if v2(d) is not None) / max(1, sum(v2(d) is not None for d in tk)) if tk else None) if cover else None
    return f

for name in ('trades', 'shadow'):
    rows = [json.loads(l) for l in open(f'{OUT}/{name}.jsonl')]
    with open(f'{OUT}/{name}_mk.jsonl', 'w') as o:
        for x in rows:
            T = x.get('trig_t') or x['t']
            o.write(json.dumps(feats(T, x['mint'])) + '\n')
    print(name, len(rows), flush=True)
