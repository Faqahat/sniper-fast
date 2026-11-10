# Per-period tables for the edge-fade question. Reads trades.jsonl + market.jsonl (built by build_trades.py).
import json, sys, collections, statistics as st, datetime
D = '/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/agent-edgefade/'
EXCL_TEMPLATE = '--excl' in sys.argv
ME = 'EgxfYgEb'
BOTS = ['8yYMhuYo', '2VggYpPu', '8PgC4ngp', '9pQQc1xy', '5ZtzVYRu', 'DL7cmioG', 'sssss', 'E2x1ewwX', 'haqq']
def isbot(u): return any(u.startswith(b) for b in BOTS)
T = [json.loads(l) for l in open(D + 'trades.jsonl')]
T.sort(key=lambda x: x['t'])
if EXCL_TEMPLATE: T = [t for t in T if not t['template']]
# period assignment
r42 = [t for t in T if t['run'] == 42]
cuts = [r42[int(len(r42) * i / 5)]['t'] for i in range(1, 5)]
def period(run, t):
    if run == 42:
        return '42.' + str(1 + sum(1 for c in cuts if t >= c))
    if run in (45, 46): return '45+46'
    return str(run)
ORDER = ['40', '41', '42.1', '42.2', '42.3', '42.4', '42.5', '43', '44', '45+46']
for t in T: t['P'] = period(t['run'], t['t'])
# market
M = collections.defaultdict(list); span = {}
for l in open(D + 'market.jsonl'):
    d = json.loads(l)
    if d.get('t') is None: 
        M[('nt', d['run'])].append(d); continue
    P = period(d['run'], d['t']); d['P'] = P; M[P].append(d)
    lo, hi = span.get(P, (d['t'], d['t'])); span[P] = (min(lo, d['t']), max(hi, d['t']))
def pkt(ns): return (datetime.datetime.utcfromtimestamp(ns / 1e9) + datetime.timedelta(hours=5)).strftime('%d %H:%M')
def med(xs):
    xs = [x for x in xs if x is not None]; return st.median(xs) if xs else float('nan')
def mean(xs):
    xs = [x for x in xs if x is not None]; return sum(xs) / len(xs) if xs else float('nan')
def q(xs, p):
    xs = sorted(x for x in xs if x is not None); return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float('nan')
rows = []
for P in ORDER:
    tt = [t for t in T if t['P'] == P]
    if not tt: continue
    lo, hi = span[P]; hrs = (hi - lo) / 3.6e12
    R = {'P': P, 'from': pkt(lo), 'to': pkt(hi), 'h': hrs, 'n': len(tt)}
    pn = [t['pnl'] / 1e6 for t in tt]
    R['avg_mSOL'] = mean(pn); R['sum_SOL'] = sum(pn) / 1e3; R['win%'] = 100 * sum(1 for x in pn if x > 0) / len(pn)
    R['med_mSOL'] = med(pn)
    R['pnl_%size'] = mean([100 * t['pnl'] / t['sol_in'] for t in tt])
    R['vsol_entry'] = mean([t['tape'][0][5] / 1e9 if t['tape'] else None for t in tt])
    R['rearm%'] = 100 * sum(1 for t in tt if t['kind'] == 'rearm') / len(tt)
    R['avg_T2'] = mean([t['pnl'] / 1e6 for t in tt if t['kind'] != 'rearm']); R['avg_rearm'] = mean([t['pnl'] / 1e6 for t in tt if t['kind'] == 'rearm'])
    # landing
    R['ms_d2land_med'] = med([t.get('ms_after_d') for t in tt]); R['ms_d2land_p75'] = q([t.get('ms_after_d') for t in tt], .75)
    R['ms_send2rx_med'] = med([t['ms_rx'] for t in tt])
    R['sameslot%'] = 100 * mean([1 if t.get('d_slot') == t['slot'] else 0 for t in tt])
    R['slots_after_trig_med'] = med([t['sat'] for t in tt])
    # competition ahead: trades between the dump and our landing
    def ahead(t, cond): return [x for x in t.get('between', []) if x[0] != ME and cond(x)]
    R['ahead_buys_avg'] = mean([len(ahead(t, lambda x: x[1])) for t in tt])
    R['ahead_buySOL_avg'] = mean([sum(x[2] for x in ahead(t, lambda x: x[1])) / 1e9 for t in tt])
    R['ahead_bot_avg'] = mean([len(ahead(t, lambda x: x[1] and isbot(x[0]))) for t in tt])
    R['first_after_dump%'] = 100 * mean([1 if not ahead(t, lambda x: x[1]) else 0 for t in tt])
    # price we paid vs dump bottom (rebound eaten before us)
    def reb(t):
        dd = t.get('d_drop')
        if dd is None: return None
        bottom = 1 - dd / 100
        bw = [x for x in t.get('between', []) if x[4] is not None]
        pre = bw[-1][4] if bw else bottom
        return 100 * (pre / bottom - 1)
    R['eaten_before_us%'] = mean([reb(t) for t in tt])
    R['dump_drop%'] = mean([t.get('d_drop') for t in tt]); R['dump_SOL'] = mean([t['d_sol'] / 1e9 if t.get('d_sol') else None for t in tt])
    R['depth_ann%'] = mean([100 * t['depth'] if t.get('depth') is not None else None for t in tt])
    R['size_SOL'] = mean([t['sol_in'] / 1e9 for t in tt])
    # followers / exit side from the tape (fill slot .. sell slot), others only
    fb, fs, fn, mx, mx3, atsell, dumpers = [], [], [], [], [], [], []
    for t in tt:
        tp = t['tape']; s0 = t['slot']; s1 = t['sell_slot'] or s0 + 2
        mine = [x for x in tp if x[0] == ME and x[1]]
        if not mine: continue
        pe = mine[0][5] / mine[0][6]  # price after our buy
        others = [x for x in tp if x[0] != ME and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s1]
        fb.append(sum(x[2] for x in others if x[1]) / 1e9); fn.append(sum(1 for x in others if x[1]))
        fs.append(sum(x[2] for x in others if not x[1]) / 1e9)
        dumpers.append(1 if any((not x[1]) and x[2] >= 1e9 for x in others) else 0)
        ps = [x[5] / x[6] for x in others]
        mx.append(100 * (max(ps) / pe - 1) if ps else 0.0)
        o3 = [x[5] / x[6] for x in tp if x[0] != ME and (x[3], x[4]) > (mine[0][3], mine[0][4]) and x[3] <= s0 + 3]
        mx3.append(100 * (max(o3) / pe - 1) if o3 else 0.0)
    R['fol_net_SOL'] = mean([a - b for a, b in zip(fb, fs)]); R['fol_buys_n'] = mean(fn); R['fol_buySOL'] = mean(fb); R['hold_sellSOL'] = mean(fs); R['hold_sell>=1SOL%'] = 100 * mean(dumpers)
    R['max_up_in_hold%'] = mean(mx); R['max_up_3slots%'] = mean(mx3); R['zero_follow%'] = 100 * mean([1 if x == 0 else 0 for x in fn])
    # market
    mm = M[P]
    R['dumps/h'] = sum(1 for d in mm if d['ev'] == 'dump') / hrs
    R['shadow_trig/h'] = sum(1 for d in mm if d['ev'] == 'presend_arm') / hrs
    R['live_arms/h'] = sum(1 for d in mm if d['ev'] == 'live_arm') / hrs
    R['fills/h'] = len(tt) / hrs
    at = [d for d in mm if d['ev'] == 'att']
    R['attempts/h'] = len(at) / hrs
    R['att_ok%'] = 100 * sum(1 for d in at if d['res'] == 'ok') / max(1, len(at))
    R['att_6042%'] = 100 * sum(1 for d in at if d['res'] == '6042') / max(1, len(at))
    R['fills/arm%'] = 100 * len(tt) / max(1, sum(1 for d in mm if d['ev'] == 'live_arm'))
    R['arm_whale%'] = mean([d['pct'] for d in mm if d['ev'] == 'live_arm'])
    R['arm_age_slots_med'] = med([d['age'] for d in mm if d['ev'] == 'live_arm'])
    # shadow control (rows a=0 ms, c=10 ms); exits carry net_cheap; map exit->period via its fill time
    rows.append(R)
# shadow per period via fill join
SH = collections.defaultdict(lambda: collections.defaultdict(list))
fillt = {}
for P in ORDER:
    for d in M.get(P, []):
        if d['ev'] == 'presend_fill': fillt[(d['run'], d['mint'], d['w'], d['row'], d['s_in'])] = (P, d)
exits = []
for k, v in M.items():
    for d in v:
        if d['ev'] == 'presend_exit': exits.append(d)
# exits have no t -> they were put in ('nt',run)
for k, v in M.items():
    if k[0] == 'nt':
        for d in v:
            if d['ev'] == 'presend_exit':
                key = (k[1], d['mint'], d['w'], d['row'], d['s_in'])
                if key in fillt:
                    P, f = fillt[key]; SH[P][d['row']].append((d['net_cheap'], f))
for R in rows:
    P = R['P']
    for row in ('a', 'c'):
        xs = SH[P][row]
        R['sh_%s_fills/h' % row] = len(xs) / R['h']
        R['sh_%s_net_SOL/h' % row] = sum(x[0] for x in xs) / R['h']
        R['sh_%s_mSOL/fill' % row] = 1000 * mean([x[0] for x in xs])
    R['sh_c_n_ahead'] = mean([x[1].get('n_ahead') for x in SH[P]['c']])
    R['live_SOL/h'] = R['sum_SOL'] / R['h']
json.dump(rows, open(D + ('rows_excl.json' if EXCL_TEMPLATE else 'rows.json'), 'w'), indent=1)
keys = [k for k in rows[0].keys() if k != 'P']
print('metric'.ljust(22) + ''.join(r['P'].rjust(9) for r in rows))
for k in keys:
    def f(v):
        if isinstance(v, str): return v.rjust(9)
        if isinstance(v, int): return str(v).rjust(9)
        return ('%.2f' % v if abs(v) < 100 else '%.0f' % v).rjust(9)
    print(k[:22].ljust(22) + ''.join(f(r[k]) for r in rows))
