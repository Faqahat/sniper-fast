#!/usr/bin/env python3
"""Landing-study's 284 landed bundles re-split by the leader's TPU ingress class as seen in fastL1 (2026-10-07):
BAM node / Harmonic front / other shared front / own TPU. The class is taken from fastL1's leaders.jsonl by identity
(the bundles are from 2026-10-04..07, so a validator may have changed setup: approximate)."""
import json, sys, os, statistics, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
H = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(H, 'bundles_landed.py')).read().split("print('n landed")[0])
L = [json.loads(l) for l in open(os.path.join(H, 'raw/leaders.jsonl'))][1:]
meta = {}
for x in L:
    meta[x['leader']] = x
def ingress(x):
    if not x: return 'unknown'
    t = x.get('tpu_quic') or ''
    if x['kind'] == 'bam' or t.endswith(':5010'): return 'BAM node'
    if (x.get('client') or '').startswith('Harmonic'): return 'Harmonic front'
    if (x.get('tpu_shared_by') or 1) > 1: return 'other shared front'
    return 'own TPU'
g = collections.defaultdict(list)
for k, o in seen.items():
    a = att.get(k)
    if not a: continue
    ldr = (o.get('landed') or {}).get('leader') or a['leader']
    near = (a['leader_rtt_ms'] or 999) < 15
    same = o['landed']['slot'] == a['trig_slot']
    g[(ingress(meta.get(ldr)), 'near' if near else 'far', 'same-slot' if same else 'later')].append(o['send_to_seen_ms'])
for k in sorted(g):
    v = sorted(g[k]); n = len(v)
    print(f"{str(k):<50} n={n:>3} p10={v[int(.1*n)]:6.1f} p50={statistics.median(v):6.1f} <50ms={sum(z<50 for z in v)/n:5.1%}")
