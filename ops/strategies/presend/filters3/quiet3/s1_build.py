#!/usr/bin/env python3
"""QUIET3 step 1: one row per LIVE position (r37..r42 = DEV+VAL only) and one row per shadow T2 trigger.
Input: the pre-send records with attempts removed (grep -v presend_attempt / presend_wide_) in EX dir.
Output: trades.jsonl (live positions with realized pnl, the arm record's signals, the tape label), shadow.jsonl.
usage: s1_build.py EXDIR OUTDIR"""
import sys, json, collections
EX, OUT = sys.argv[1], sys.argv[2]
ME = 'EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR'
VAL_T = 1793516400 * 10**9          # 11-01 12:00 PKT
RUNS = [37, 38, 39, 40, 41, 42]

def split(t): return 'VAL' if t >= VAL_T else 'DEV'

trades, shadow = [], []
for r in RUNS:
    arms = collections.defaultdict(list)       # (mint, kind) -> live arms in order
    fills = {}; closes = []; realized = collections.defaultdict(list); tape = collections.defaultdict(list)
    disarms = collections.defaultdict(list)
    sh_arm = {}; sh_fill = {}; sh_exit = {}; sh_dis = {}; live_by_sig = {}; skip_by_sig = {}
    for l in open(f'{EX}/r{r}.jsonl'):
        d = json.loads(l); ev = d['ev']
        if ev == 'presend_live_arm':
            k = d.get('kind') or 'T2'; arms[(d['mint'] if 'mint' in d else d['trig']['mint'], k)].append(d)
            if k == 'T2': live_by_sig[d['trig']['sig']] = d
        elif ev == 'presend_live_skip':
            if (d.get('kind') or 'T2') == 'T2' and 'trig' in d: skip_by_sig[d['trig']['sig']] = d
        elif ev == 'presend_live_fill': fills[d['sig']] = d
        elif ev == 'presend_live_close': closes.append(d)
        elif ev == 'presend_live_realized': realized[(d['mint'], d.get('pid'))].append(d)
        elif ev == 'presend_live_tape': tape[d['mint']].append(d)
        elif ev == 'presend_live_disarm': disarms[(d['mint'], d.get('kind') or 'T2', d.get('w'))].append(d)
        elif ev == 'presend_arm': sh_arm[(d['mint'], d['w'])] = d
        elif ev == 'presend_fill' and d.get('row') == 'c': sh_fill[(d['mint'], d['w'])] = d
        elif ev == 'presend_exit' and d.get('row') == 'c': sh_exit[(d['mint'], d['w'])] = d
        elif ev == 'presend_disarm': sh_dis[(d['mint'], d['w'])] = d
    used = collections.Counter()
    for c in closes:
        key = (c['mint'], c.get('pid')); rl = realized[key][used[key]] if used[key] < len(realized[key]) else None
        used[key] += 1
        b0 = c['buys'][0]; kind = c.get('kind') or 'T2'; f = fills.get(b0['sig'], {})
        # the arm of this window: same mint+kind+w, last one before the buy
        cand = [a for a in arms[(c['mint'], kind)] if a.get('w') == c.get('w')]
        arm = None
        for a in cand:
            ta = (a.get('trig') or a.get('dump') or {}).get('t', 0)
            if ta <= b0['t']: arm = a
        trig = (arm or {}).get('trig') or (arm or {}).get('dump') or {}
        whales = set()
        if kind == 'T2' and trig.get('wallet'): whales.add(trig['wallet'])
        for h in (arm or {}).get('holders') or []: whales.add(h['w'])
        sl = c.get('sell_lands') or ([c['sell_land']] if c.get('sell_land') else [])
        last_sell = max(((x[0], x[1]) for x in sl), default=None)
        mybuys = sorted((b['slot'], b['idx']) for b in c['buys'])
        first = mybuys[0]
        tp = sorted({(x['slot'], x['idx'], x.get('j', 0)): x for x in tape[c['mint']]}.values(), key=lambda x: (x['slot'], x['idx']))
        # tape rows of this position: from our first buy to sell + 12 slots
        endp = last_sell or (first[0] + 3, 10**6)
        fol = []; fol_hold = []; sells_hold = 0.0; pre_slot_buys = []
        for x in tp:
            p = (x['slot'], x['idx'])
            if x['user'] == ME or x['user'] in whales: continue
            if x['slot'] == first[0] and p < first and x['buy']: pre_slot_buys.append(x['sol'])
            if p <= first or x['slot'] > first[0] + 12: continue
            if x['buy']:
                fol.append((x['slot'] - first[0], x['sol'], x['user'][:8], p <= endp))
                if p <= endp: fol_hold.append(x['sol'])
            elif p <= endp: sells_hold += x['sol']
        tape_max = max((x['slot'] for x in tp if x['slot'] >= first[0] and x['slot'] <= first[0] + 200), default=first[0]) - first[0]
        row = {'run': r, 'split': split(b0['t']), 't': b0['t'], 'mint': c['mint'], 'kind': kind, 'w': c.get('w'), 'pid': c.get('pid'),
               'pnl': rl['pnl'] if rl else None, 'nbuys': len(c['buys']), 'sol_in': sum(b['sol_in'] for b in c['buys']),
               'slot': first[0], 'idx': first[1], 'sell': last_sell, 'exit_why': c.get('exit_why'), 'result': c.get('result'),
               'sat': f.get('slots_after_trigger'), 'trig_slot': trig.get('slot'), 'trig_t': trig.get('t'), 'trig_sig': trig.get('sig'),
               'whale': trig.get('wallet') or trig.get('seller'), 'pct': trig.get('pct'), 'trig_sol': trig.get('sol'), 'age_slots': trig.get('age_slots'),
               'vsol': trig.get('vsol'), 'quiet': (arm or {}).get('quiet'), 'v2': (arm or {}).get('v2'), 'ann': (arm or {}).get('ann'),
               'nb': (arm or {}).get('nb'), 'holders': (arm or {}).get('holders'), 'arm_found': arm is not None,
               'fol': fol, 'n_fol_hold': len(fol_hold), 'sol_fol_hold': sum(fol_hold) / 1e9, 'sells_hold': sells_hold / 1e9,
               'pre_slot_buys': len(pre_slot_buys), 'tape_max': tape_max,
               'fol10': len({u for s_, so, u, h in fol if s_ <= 10}), 'fol10_big': len({u for s_, so, u, h in fol if s_ <= 10 and so >= 0.1e9})}
        trades.append(row)
    # shadow T2 triggers (paper of every trigger) with the live decision
    for (m, w), a in sh_arm.items():
        sig = a.get('sig'); la = live_by_sig.get(sig); sk = skip_by_sig.get(sig)
        fx = sh_exit.get((m, w)); fl = sh_fill.get((m, w))
        shadow.append({'run': r, 'split': split(a['t']), 't': a['t'], 'mint': m, 'w': w, 'sig': sig, 'whale': a.get('wallet'), 'pct': a.get('pct'),
                       'sol': a.get('sol'), 'age_slots': a.get('age_slots'), 'vsol': a.get('vsol'), 'slot': a.get('slot'),
                       'quiet': a.get('quiet'), 'v2': a.get('v2'), 'rows_c': (a.get('rows') or {}).get('c'),
                       'live': 'arm' if la else ('skip:' + sk['why'] if sk else None),
                       'ann': (la or sk or {}).get('ann'), 'nb': (la or sk or {}).get('nb'),
                       'c_fill': fl is not None, 'c_net': fx.get('net_cheap') if fx else None, 'c_why': fx.get('why') if fx else None,
                       'c_s_in': fl.get('s_in') if fl else None, 'c_drop': fl.get('drop_pct') if fl else None,
                       'qstop': (sh_dis.get((m, w)) or {}).get('quiet_stop')})
    print(r, 'positions', sum(1 for t in trades if t['run'] == r), 'shadow', sum(1 for s in shadow if s['run'] == r), flush=True)
with open(f'{OUT}/trades.jsonl', 'w') as o:
    for t in trades: o.write(json.dumps(t) + '\n')
with open(f'{OUT}/shadow.jsonl', 'w') as o:
    for t in shadow: o.write(json.dumps(t) + '\n')
