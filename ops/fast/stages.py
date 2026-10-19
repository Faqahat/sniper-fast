#!/usr/bin/env python3
"""per-stage p50/p99 from a --lat-trace file (fast binary) or the old binary's dry log.  usage: stages.py trace|old <file>"""
import sys, json, re, collections
def q(v, x):
    v = sorted(v); return v[min(len(v) - 1, int(round((len(v) - 1) * x)))] if v else float('nan')
def row(name, v, unit=1.0):
    v = [x / unit for x in v if x is not None]
    print(f'{name:44} n={len(v):5d}  p50 {q(v,.5):9.1f}  p90 {q(v,.9):9.1f}  p99 {q(v,.99):9.1f}  max {max(v) if v else float("nan"):9.1f}')
mode, f = sys.argv[1], sys.argv[2]
if mode == 'old':
    b, r = [], []
    for l in open(f, errors='replace'):
        m = re.search(r'JUNK-FAN .*build_us=(\d+)', l)
        if m: b.append(int(m.group(1)))
        m = re.search(r'  FIRE slot=.*rx_to_fire_us=(\d+)', l)
        if m: r.append(int(m.group(1)))
    print('OLD binary (µs)'); row('build+sign (JUNK-FAN build_us)', b); row('create rx -> fire point (rx_to_fire_us)', r)
    sys.exit()
P, F = [], []
for l in open(f):
    try: v = json.loads(l)
    except Exception: continue
    (P if v['ev'] == 'prep' else F).append(v)
print(f'{len(P)} prepared creates, {len(F)} fires (µs)')
cr = [p for p in P if p.get('dec_to_deq_us', 0) is not None and p.get('deq_to_detect_ns', 0) > 0]
row('create: feed decoded -> loop dequeue', [p['dec_to_deq_us'] for p in cr])
row('create: dequeue -> detect_launch done', [p['deq_to_detect_ns'] for p in cr], 1e3)
row('create: detect -> gates passed', [p['detect_to_gated_ns'] for p in cr], 1e3)
row('create: gates -> prepare start (min_out)', [p['gated_to_prep_ns'] for p in cr], 1e3)
for k, n in [('route_ns', 'prep: route+tips+blockhash'), ('derive_ns', 'prep: derive 2 ATAs'), ('patch_ns', 'prep: template patch'), ('sign_ns', 'prep: sign'),
             ('encode_ns', 'prep: encode+frame every path'), ('prep_ns', 'prep: TOTAL (tx + every request ready)')]:
    row(n, [p[k] for p in P], 1e3)
row('create: dequeue -> tx ready (detect+gates+prep)', [p['deq_to_detect_ns'] + p['detect_to_gated_ns'] + p['gated_to_prep_ns'] + p['prep_ns'] for p in cr], 1e3)
row('fire: deciding tx decoded -> dequeue', [x['ev_dec_to_deq_us'] for x in F if x['ev_dec_to_deq_us'] < 10**6])
row('fire: deciding tx dequeue -> decision', [x['ev_deq_to_decide_ns'] for x in F], 1e3)
row('fire: create dequeue -> decision (gate wait)', [x['create_deq_to_decide_us'] for x in F])
row('fire: decision -> fire start', [x['decide_to_fire_ns'] for x in F], 1e3)
row('fire: decision -> FIRST write() returned', [x['decide_to_first_write_ns'] for x in F if x['decide_to_first_write_ns']], 1e3)
row('fire: decision -> LAST write() returned', [max(w['from_decide_ns'] for w in x['writes'] if w['status'] in ('written', 'spawned')) for x in F], 1e3)
row('fire: deciding tx dequeue -> FIRST write', [x['ev_deq_to_decide_ns'] + x['decide_to_first_write_ns'] for x in F if x['decide_to_first_write_ns']], 1e3)
if any(x.get('kick_age_us') is not None for x in F): row('fire: last pre-kick age at the fire', [x['kick_age_us'] for x in F])
per = collections.defaultdict(list); dur = collections.defaultdict(list)
for x in F:
    for w in x['writes']:
        if w['status'] == 'written': per[w['path']].append(w['from_decide_ns']); dur[w['path']].append(w['done_ns'] - w['start_ns'])
for k in sorted(per): row(f'  {k}: decision -> write() returned', per[k], 1e3)
for k in sorted(dur): row(f'  {k}: the write() itself', dur[k], 1e3)
st = collections.Counter(w['status'] for x in F for w in x['writes'])
print('write statuses:', dict(st), '| fast_built:', collections.Counter(p['fast_built'] for p in P), '| verify:', collections.Counter(str(p['verify']) for p in P))
