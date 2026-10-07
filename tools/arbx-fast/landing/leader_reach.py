#!/usr/bin/env python3
"""Leader slots of fastL1-p1 (30 min, 6,804 slots from leaders.jsonl) by kind, client, leader TPU-QUIC RTT from Cherry,
and whether the leader's gossip/TPU IP is a DoubleZero IBRL user (doublezero user list, read on Cherry) - i.e. whether
an IBRL tunnel from Cherry could reach its TPU over DZ. Also whether the advertised TPU is shared (a relayer / BAM
front). Inputs: raw/leaders.jsonl, raw/dz-users.txt, raw/cluster-nodes.json (public getClusterNodes, 2026-10-07)."""
import json, collections, os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')
L = [json.loads(l) for l in open(os.path.join(D, 'leaders.jsonl'))][1:]
slots = {x['slot']: x for x in L}
cn = {n['pubkey']: n for n in json.load(open(os.path.join(D, 'cluster-nodes.json')))['result']}

ibrl_ips, mc_ips = set(), set()
hdr = None
for line in open(os.path.join(D, 'dz-users.txt')):
    cols = [c.strip() for c in line.split('|')]
    if 'user_type' in cols:
        hdr = cols
        continue
    if not hdr or len(cols) != len(hdr):
        continue
    r = dict(zip(hdr, cols))
    if r.get('status') != 'activated':
        continue
    tgt = ibrl_ips if r['user_type'].startswith('IBRL') else mc_ips
    for k in ('client_ip', 'dz_ip'):
        if r.get(k):
            tgt.add(r[k])


def ip(addr):
    return addr.rsplit(':', 1)[0] if addr else None


def rb(r):
    if r is None:
        return '?'
    for lim in (5, 15, 30, 50, 100, 200):
        if r < lim:
            return f'<{lim}'
    return '>=200'


n = len(slots)
c = collections.Counter()
for s, x in slots.items():
    node = cn.get(x['leader'], {})
    g, t = ip(node.get('gossip')), ip(node.get('tpuQuic'))
    on_dz = (g in ibrl_ips) or (t in ibrl_ips)
    tpu_on_dz = t in ibrl_ips
    shared = (x.get('tpu_shared_by') or 1) > 1
    c[('kind', x['kind'])] += 1
    c[('rtt', rb(x['rtt_ms']))] += 1
    c[('kind,rtt', x['kind'], rb(x['rtt_ms']))] += 1
    c[('dz gossip-or-tpu ip is IBRL user', on_dz)] += 1
    c[('dz advertised TPU ip is IBRL user', tpu_on_dz)] += 1
    c[('kind,TPU shared (relayer/front)', x['kind'], shared)] += 1
    c[('kind,dz', x['kind'], on_dz)] += 1
    c[('rtt<30, kind, dz', (x['rtt_ms'] or 999) < 30, x['kind'], on_dz)] += 1
    c[('client', x['client'])] += 1
print('slots', n, ' IBRL ips', len(ibrl_ips), ' multicast ips', len(mc_ips))
for k in sorted(c, key=str):
    print(f"  {str(k):<60} {c[k]:>5} {100*c[k]/n:5.1f}%")


# --- ingress class: who sits in front of the leader's TPU (port 5010 = BAM node; Harmonic remote TPU on :9007 shared;
#     own TPU = not shared). Then x RTT.
def ingress(x):
    t = x.get('tpu_quic') or ''
    shared = (x.get('tpu_shared_by') or 1) > 1
    if x['kind'] == 'bam' or t.endswith(':5010'):
        return 'BAM node'
    if (x.get('client') or '').startswith('Harmonic'):
        return 'Harmonic front'
    if shared:
        return 'other shared front (relayer?)'
    return 'own TPU (no front)'


print('\ningress class x leader TPU RTT (share of slots)')
c2 = collections.Counter((ingress(x), rb(x['rtt_ms'])) for x in slots.values())
tot = collections.Counter(ingress(x) for x in slots.values())
for cls in sorted(tot):
    parts = ' '.join(f"{b}:{100*c2[(cls,b)]/n:.1f}" for b in ['<5', '<15', '<30', '<50', '<100', '<200', '>=200', '?'])
    print(f"  {cls:<32} {100*tot[cls]/n:5.1f}%   {parts}")
