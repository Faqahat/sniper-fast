#!/usr/bin/env python3
"""fastL1-p1: per landed copy, send -> first seen in our shred feeds, by path / leader kind / region / slot offset
/ time into slot. Inputs are local, read-only extracts of Cherry's /root/arbx-fast/runs/fastL1/fastL1-p1 streams
(see raw/). Usage: python3 fastl1_landed.py raw/ > fastl1_landed.out"""
import json, sys, statistics, collections, os

D = sys.argv[1] if len(sys.argv) > 1 else 'raw'
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def b58d(s):
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return b'\0' * (len(s) - len(s.lstrip('1'))) + b


def jl(name):
    return [json.loads(l) for l in open(os.path.join(D, name)) if l.strip()][1:]


attempts = {x['attempt']: x for x in jl('attempts.jsonl')}
copies = jl('copies.jsonl')
outcomes = {x['attempt']: x for x in jl('outcomes.jsonl')}
sig8_copy = {b58d(c['sig'])[:8].hex(): c for c in copies}
# several copies may share a sig (jito-bundle + helius share the primary tx); keep all
sig8_copies = collections.defaultdict(list)
for c in copies:
    sig8_copies[b58d(c['sig'])[:8].hex()].append(c)

# txarr: sig8 slot first_ns per-feed offsets (us) ; feeds dz-leader, dz-retransmit-eu, haan-deshred, haan-grpc
FEEDS = ['dz-leader', 'dz-retransmit-eu', 'haan-deshred', 'haan-grpc']
arr = {}
for l in open(os.path.join(D, 'txarr_ours.log')):
    p = l.split()
    if len(p) < 3 or p[0].startswith('#'):
        continue
    offs = p[3:]
    first_feed = next((FEEDS[i] for i, v in enumerate(offs) if v == '0'), None)
    arr[p[0]] = dict(slot=int(p[1]), first_ns=int(p[2]), first_feed=first_feed)

poh = {}
for l in open(os.path.join(D, 'poh_ours.log')):
    p = l.split()
    poh.setdefault(p[0], float(p[2]))

# slot first-shred time (our clock) = min t_first over shred feeds
slot_first = {}
for l in open(os.path.join(D, 'slots-feed.log')):
    if l.startswith('#'):
        continue
    p = l.split()
    try:
        s, t = int(p[1]), int(p[5])
    except Exception:
        continue
    if t > 0 and (s not in slot_first or t < slot_first[s]):
        slot_first[s] = t
slots_sorted = sorted(slot_first)

# leaders / validators: region, client, kind, rtt per identity (latest)
vinfo = {}
for x in jl('validators.jsonl'):
    vinfo[x['identity']] = x
linfo = {}
slot_leader = {}
for x in jl('leaders.jsonl'):
    if x.get('slot') is not None and x.get('leader'):
        slot_leader[x['slot']] = x['leader']
    if x.get('leader'):
        prev = linfo.get(x['leader'], {})
        merged = dict(prev)
        merged.update({k: v for k, v in x.items() if v is not None})
        linfo[x['leader']] = merged


def leader_meta(ident):
    m = {}
    m.update({k: v for k, v in vinfo.get(ident, {}).items() if v is not None})
    m.update({k: v for k, v in linfo.get(ident, {}).items() if v is not None})
    return m


def slot_at(t):
    # latest slot whose first shred arrived at or before t
    import bisect
    best = None
    for s in slots_sorted:
        pass
    return best


# precompute (t, slot) sorted by time
ts = sorted((t, s) for s, t in slot_first.items())
import bisect
tlist = [t for t, _ in ts]


def cur_slot(t):
    i = bisect.bisect_right(tlist, t) - 1
    if i < 0:
        return None, None
    # the highest slot started at or before t
    best = max(ts[max(0, i - 8):i + 1], key=lambda z: z[1])
    return best[1], (t - best[0]) / 1e6


rows = []
for s8, a in arr.items():
    cs = sig8_copies.get(s8)
    if not cs:
        continue
    c = [k for k in cs if k['path'] != 'jito-bundle'] or cs
    c = c[0]
    att = attempts.get(c['attempt'], {})
    out = outcomes.get(c['attempt'], {})
    landed = out.get('landed') or {}
    ldr = slot_leader.get(a['slot']) or landed.get('leader')
    rec_ldr = landed.get('leader')
    lm = leader_meta(ldr) if ldr else {}
    # all copies of this attempt and their send times
    sib = [k for k in copies if k['attempt'] == c['attempt']]
    t_first_send = min(k['t_sent'] for k in sib)
    cs_slot, into = cur_slot(c['t_sent'])
    trig_slot = (att.get('trigger') or {}).get('slot')
    rows.append(dict(
        attempt=c['attempt'], path=c['path'], tip=c.get('tip_lamports'), band=att.get('band'),
        send_ms=(a['first_ns'] - c['t_sent']) / 1e6,
        send_ms_first_copy=(a['first_ns'] - t_first_send) / 1e6,
        copy_spread_ms=(max(k['t_sent'] for k in sib) - t_first_send) / 1e6,
        paths_sent=','.join(sorted(k['path'] for k in sib)),
        first_feed=a['first_feed'], slot=a['slot'], trig_slot=trig_slot,
        target_slot=out.get('target_slot'), cur_slot_at_send=cs_slot, ms_into_slot_at_send=into,
        slots_after_send=(a['slot'] - cs_slot) if cs_slot else None,
        leader=ldr, rec_leader_mismatch=(rec_ldr is not None and rec_ldr != ldr), kind=lm.get('kind'),
        leader_at_send=slot_leader.get(cs_slot), same_leader_as_send=(slot_leader.get(cs_slot) == ldr),
        leader_window_pos=None,
        region=lm.get('region') or lm.get('city'), client=lm.get('client'), rtt=lm.get('rtt_ms'),
        tpu_shared_by=lm.get('tpu_shared_by'), poh_ms=poh.get(s8),
        att_leader=(att.get('leader') or {}).get('leader'),
        att_leader_kind=(att.get('leader') or {}).get('kind'),
    ))

for r in rows:
    # position of the landed slot in its leader's 4-slot window, and of the send slot
    r['leader_window_pos'] = r['slot'] % 4
    r['send_window_pos'] = r['cur_slot_at_send'] % 4 if r['cur_slot_at_send'] else None
rows.sort(key=lambda r: r['send_ms'])
print('mismatches outcome.landed.leader vs slot leader:', [(r['attempt'], r['slot']) for r in rows if r['rec_leader_mismatch']])
print('attempt path      send->seen  kind  region           client          rtt   slot-cur slot+  into  poh   feed  tip')
for r in rows:
    print(f"{r['attempt']:>4} {r['path']:<10} {r['send_ms']:8.1f}  {str(r['kind']):<5} {str(r['region'])[:16]:<16} "
          f"{str(r['client'])[:14]:<14} {r['rtt'] if r['rtt'] is None else round(r['rtt'],1)!s:>5} "
          f"{r['slots_after_send']!s:>3} {r['slot'] - (r['trig_slot'] or r['slot'])!s:>3}(trig) "
          f"{r['ms_into_slot_at_send'] if r['ms_into_slot_at_send'] is None else round(r['ms_into_slot_at_send'])!s:>4} "
          f"{r['poh_ms']!s:>7} {r['first_feed']:<16} win={r['send_window_pos']}->{r['leader_window_pos']} sameldr={int(r['same_leader_as_send'])} {r['leader'][:8]}")


def summ(name, key):
    g = collections.defaultdict(list)
    for r in rows:
        g[key(r)].append(r['send_ms'])
    print(f"\n{name}:")
    for k, v in sorted(g.items(), key=lambda kv: statistics.median(kv[1])):
        v.sort()
        print(f"  {str(k):<28} n={len(v):>2} median={statistics.median(v):7.1f} min={v[0]:7.1f} max={v[-1]:7.1f} <50ms={sum(1 for z in v if z < 50)}")


summ('all', lambda r: 'all')
summ('by landed path', lambda r: r['path'])
summ('by leader kind', lambda r: r['kind'])
summ('by leader region', lambda r: r['region'])
summ('by client', lambda r: r['client'])
summ('by slots after the slot current at send', lambda r: r['slots_after_send'])
summ('by ms into slot at send (bucket)', lambda r: None if r['ms_into_slot_at_send'] is None else int(r['ms_into_slot_at_send'] // 100) * 100)
summ('same leader as at send (landed within the current leader window)', lambda r: r['same_leader_as_send'])
summ('send slot position in leader window (0-3)', lambda r: r['send_window_pos'])
summ('kind x path', lambda r: (r['kind'], r['path']))
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fastl1_landed.json'), 'w'), indent=1)
