#!/usr/bin/env python3
# classify every fire + latency gap to the crossing (read-only)
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/agents/headtohead/work")
W = "/home/moiz/sniper/ops/agents/headtohead/work"
o = json.load(open(W + "/fires_h2h.json"))
L = json.load(open('/home/moiz/sniper/ops/dip/speed/leaders/leader_rtt_new.json'))['leaders']
TAPE = collections.defaultdict(list)
for r in range(1, 6):
    for l in open(f"/home/moiz/sniper/ops/dip/speed/dip_r{r}.jsonl"):
        d = json.loads(l)
        if d["ev"] == "tape": TAPE[(d["mint"], d["slot"])].append((d["idx"], d["t"]))
def interp_rx(mint, s, i, t0):
    """exec-feed rx of a block position from the neighbouring tape rows (ms after dump exec rx)"""
    rows = sorted(TAPE.get((mint, s), []))
    before = [t for (j, t) in rows if j < i]; after = [t for (j, t) in rows if j > i]
    lo = (max(before) - t0) / 1e6 if before else None; hi = (min(after) - t0) / 1e6 if after else None
    return lo, hi
res = []
for x in o:
    f = x['f']; seq = x['seq']; t = f.get('timing') or {}
    us = seq[x['usk']] if x['usk'] is not None else None
    cr = seq[x['cross']] if x['cross'] is not None else None
    t0 = f['t_dump_rx']
    our_first = (t['buy_first_rx'] - t0) / 1e6 if t.get('buy_first_rx') else None
    our_exec = us['rx_ms'] if us and us['rx_ms'] is not None else None
    lo = hi = None
    if us and our_exec is None: lo, hi = interp_rx(f['mint'], us['s'], us['i'], t0)
    if f['result'] == 'sold': cat = 'FILL_S' if us['ds'] == 0 else 'FILL_S1'
    elif us and us['ec'] and us['ec'].endswith('6001'): cat = 'DEADLINE'
    elif us and cr:
        if us['ds'] == 0: cat = 'LOST_S_samblock'        # landed in dump block, behind the crossing
        elif cr['ds'] == 0: cat = 'LOST_S1_crossedInS'   # missed dump block; price crossed in it
        else: cat = 'LOST_S1_crossedInS1'                # both in S+1, crossing before us
    else: cat = 'OTHER'
    nb_before_cross = sum(1 for z in seq[:(x['cross'] + 1) if x['cross'] is not None else len(seq)] if z['kind'] == 'BUY' and not z['us'])
    res.append(dict(run=f['run'], mint=f['mint'][:8], cat=cat, client=f['client'], route=f['route'], leader=f['leader'][:6], rtt=L.get(f['leader'], {}).get('rtt'),
                    pos=x['S'] % 4, iD=x['iD'], us_ds=us['ds'] if us else None, us_i=us['i'] if us else None, our_first=our_first, our_exec=our_exec, our_interp=(lo, hi),
                    cr_ds=cr['ds'] if cr else None, cr_i=cr['i'] if cr else None, cr_rx=cr['rx_ms'] if cr else None, cr_payer=cr['payer'][:8] if cr else None,
                    react=t.get('reaction_ms'), f2s=t.get('fire_to_seen_ms'), exec_lag=t.get('exec_lag_ms'), nb_before_cross=nb_before_cross,
                    paths='+'.join(w['path'] for w in f['writes']), hour_pkt=((t0 // 10**9) + 5 * 3600) % 86400 // 3600, dump_sol=x['dump_sol'] / 1e9))
json.dump(res, open(W + "/fires_cat.json", "w"))
c = collections.Counter(r['cat'] for r in res)
print("categories:", dict(c))
print("\nLOST cases: our rx vs crossing rx (ms after dump exec-rx). our_first=first-feed rx of our tx; interp=exec-feed bracket from neighbours")
for r in res:
    if r['cat'].startswith('LOST') or r['cat'].startswith('FILL'):
        print("%-20s r%d %s %-18s pos%d us %s/%s first=%s interp=%s | cross %s/%s rx=%s %s | need=%s" % (
            r['cat'], r['run'], r['mint'], r['client'], r['pos'], r['us_ds'], r['us_i'], '%.1f' % r['our_first'] if r['our_first'] is not None else '-',
            '(%s,%s)' % tuple('%.1f' % v if v is not None else '-' for v in r['our_interp']), r['cr_ds'], r['cr_i'], '%.1f' % r['cr_rx'] if r['cr_rx'] is not None else '-', r['cr_payer'],
            '%.1f' % (r['our_first'] - r['cr_rx']) if r['our_first'] is not None and r['cr_rx'] is not None else '-'))
