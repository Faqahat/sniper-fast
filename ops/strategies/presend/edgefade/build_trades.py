# Build one row per live trade (r40..r46) + per-period market/shadow series. Writes trades.jsonl, market.jsonl.
import json, sys, collections
BASE = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/'
LIVE = BASE + 'r42b/r%dlive.jsonl'
EX = BASE + 'agent-edgefade/ex/r%d.jsonl'
OUT = BASE + 'agent-edgefade/'
ME = 'EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR'
TEMPLATE = 'F7AGag2L GUzXPKkF DdnwSojA JBbLfvEj Ay7GZ155 7XYFguf5 2TnA382v 8C8Yn9ap 3pf6qQ3D 9yV66yPP 64FZvuaL 49knqC2b EVhNMiwu'.split()
RUNS = [40, 41, 42, 43, 44, 45, 46]
trades = []; market = []
for r in RUNS:
    fills = {}; closes = []; realized = collections.defaultdict(list); tape = collections.defaultdict(list)
    arms = []; skips = []; disarms = []
    for l in open(LIVE % r):
        d = json.loads(l); ev = d['ev']
        if ev == 'presend_live_fill': fills[d['sig']] = d
        elif ev == 'presend_live_close': closes.append(d)
        elif ev == 'presend_live_realized': realized[(d['mint'], d.get('pid'))].append(d)
        elif ev == 'presend_live_tape': tape[d['mint']].append(d)
        elif ev == 'presend_live_arm': arms.append(d)
        elif ev == 'presend_live_disarm': disarms.append(d)
        elif ev == 'presend_live_skip': skips.append(d)
    # landed attempts by sig, plus all attempts summary
    land = {}; atts = []
    for l in open(EX % r):
        d = json.loads(l); ev = d['ev']
        if ev == 'presend_attempt_land':
            atts.append((d['t'] or d['t_send'], d['res'], d.get('kind'), d['ms_send_to_rx']))
            if d['sig'] in fills: land[d['sig']] = d
        elif ev in ('dump', 'presend_arm', 'presend_fill', 'presend_exit', 'presend_disarm', 'presend_skip'):
            market.append(dict(d, run=r))
    for (t, res, kind, ms) in atts:
        market.append({'ev': 'att', 'run': r, 't': t, 'res': res, 'kind': kind, 'ms': ms})
    for a in arms:
        tg = a.get('trig') or a.get('dump')
        market.append({'ev': 'live_arm', 'run': r, 't': tg['t'], 'kind': a.get('kind') or 'T2', 'pct': tg['pct'], 'age': tg['age_slots'], 'mint': a['mint'] if 'mint' in a else tg['mint'], 'drop': tg.get('drop_pct')})
    for a in disarms:
        market.append({'ev': 'live_disarm', 'run': r, 'filled': a.get('filled'), 'why': a.get('why'), 'kind': a.get('kind'), 'mint': a.get('mint'), 'slot': a.get('slot')})
    for a in skips:
        tt = (a.get('trig') or a.get('dump') or {}).get('t')
        market.append({'ev': 'live_skip', 'run': r, 't': tt, 'why': a.get('why'), 'kind': a.get('kind')})
    used = collections.Counter()
    for c in closes:
        key = (c['mint'], c.get('pid'))
        rl = realized[key][used[key]] if used[key] < len(realized[key]) else None
        used[key] += 1
        b0 = c['buys'][0]; f = fills.get(b0['sig'], {})
        L = land.get(b0['sig'])
        row = {'run': r, 't': b0['t'], 'mint': c['mint'], 'pnl': rl['pnl'] if rl else None, 'kind': c.get('kind') or 'T2',
               'template': any(c['mint'].startswith(p) for p in TEMPLATE), 'nbuys': len(c['buys']),
               'sol_in': sum(b['sol_in'] for b in c['buys']), 'slot': b0['slot'], 'sell_slot': (c.get('sell_land') or [None])[0],
               'exit_why': c.get('exit_why'), 'held_s': c.get('held_s'), 'path': c.get('path'), 'client': c.get('client'),
               'sat': f.get('slots_after_trigger'), 'sas': f.get('slots_after_send'), 'ms_rx': f.get('ms_send_to_rx'),
               'n_try': f.get('n'), 'p_pre': f.get('p_entry_pre'), 'p_post': f.get('p_entry_post'), 'p_sign': f.get('p_sign'), 'lim': f.get('lim'),
               'depth': (f.get('ann') or {}).get('depth'), 'ob6': (f.get('ann') or {}).get('ob6'), 'idx': f.get('idx')}
        if L:
            row['ms_after_d'] = L.get('ms_after_d_rx'); row['d_drop'] = L['d'].get('drop_pct'); row['d_sol'] = L['d'].get('sol')
            row['d_slot'] = L['d'].get('slot'); row['between'] = L['between']; row['after'] = L['after']
        # tape after our fill (ours and others) until our sell
        tp = sorted(tape[c['mint']], key=lambda x: (x['slot'], x['idx']))
        row['tape'] = [[x['user'][:8], x['buy'], x['sol'], x['slot'], x['idx'], x['vsol'], x['vtok'], x['t']] for x in tp]
        trades.append(row)
with open(OUT + 'trades.jsonl', 'w') as o:
    for t in trades: o.write(json.dumps(t) + '\n')
with open(OUT + 'market.jsonl', 'w') as o:
    for t in market: o.write(json.dumps(t) + '\n')
print(len(trades), len(market), sum(1 for t in trades if 'between' in t), sum(1 for t in trades if t['pnl'] is None))
