#!/usr/bin/env python3
"""Landing-study campaigns (FT-006..FT-013b, 284 landed Jito bundles, all sent to the Frankfurt block engine):
send -> first seen in our shred feeds, split by leader kind x leader RTT from Frankfurt, client, landed slot vs trigger
slot. Read-only over /home/moiz/arbx-offload (local copies). Joins attempts_all.jsonl (leader meta) with outcomes."""
import sys, json, statistics, collections
sys.path.insert(0, '/home/moiz/arbx-offload/landing-study/scripts')
from rd import segments, stream  # noqa

segs = list(segments()) + [("ft012b", "ft012b-p1", "/home/moiz/arbx-offload/landing-study/raw/ft012b/ft012b-p1")]
seen = {}
for camp, seg, d in segs:
    for o in stream(d, "outcomes"):
        if o.get("final") == "landed_ok" and o.get("send_to_seen_ms") is not None:
            seen[(seg, o["attempt"])] = o
att = {}
for l in open('/home/moiz/arbx-offload/landing-study/out/attempts_all.jsonl'):
    x = json.loads(l)
    att[(x['seg'], x['attempt'])] = x

rows = []
for k, o in seen.items():
    a = att.get(k)
    if not a:
        continue
    rows.append(dict(ms=o['send_to_seen_ms'], kind=a['leader_kind'], client=a['leader_client'], region=a['leader_region'],
                     rtt=a['leader_rtt_ms'], dslot=(o['landed']['slot'] - a['trig_slot']) if o.get('landed') else None,
                     tsl=(o['landed']['slot'] - a['target_slot']) if o.get('landed') else None,
                     poh=(o.get('poh') or {}).get('ours', {}) and (o.get('poh') or {}).get('ours', {}).get('ms')))
print('n landed with send->seen:', len(rows))


def rb(r):
    if r is None:
        return '?'
    for lim in (5, 15, 30, 80, 150):
        if r < lim:
            return f'<{lim}'
    return '>=150'


def q(v):
    v = sorted(v)
    n = len(v)
    return f"n={n:>3} p10={v[int(.1*n)]:6.1f} p50={statistics.median(v):6.1f} p90={v[min(n-1,int(.9*n))]:6.1f} <50ms={sum(1 for z in v if z < 50)/n:5.1%} <30ms={sum(1 for z in v if z < 30)/n:5.1%}"


def show(title, key):
    g = collections.defaultdict(list)
    for r in rows:
        g[key(r)].append(r['ms'])
    print('\n' + title)
    for k in sorted(g, key=str):
        print(f"  {str(k):<28} {q(g[k])}")


show('all', lambda r: 'all')
show('kind', lambda r: r['kind'])
show('kind x leader TPU RTT (ms)', lambda r: (r['kind'], rb(r['rtt'])))
show('client', lambda r: r['client'])
show('client (RTT<15ms only)', lambda r: r['client'] if (r['rtt'] or 999) < 15 else 'far')
show('landed slot - trigger slot', lambda r: r['dslot'])
show('kind x (landed slot - trigger slot) (RTT<15)', lambda r: (r['kind'], r['dslot']) if (r['rtt'] or 999) < 15 else 'far')
pv = [r['poh'] for r in rows if r['poh'] is not None]
print('\nPoH position of our landed bundle in its slot (ms):', len(pv), sorted(pv)[len(pv)//2] if pv else None)

print('\nPoH position of landed bundle in its slot, by kind and slot offset:')
g = collections.defaultdict(list)
for r in rows:
    if r['poh'] is not None:
        g[(r['kind'], r['dslot'])].append((round(r['poh']), round(r['ms'])))
for k in sorted(g, key=str):
    print(' ', k, sorted(g[k]))
