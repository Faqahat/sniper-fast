#!/usr/bin/env python3
"""QUIET3 scorer (FILTERS-3, quiet3 agent, 11-03). Reads pre-send record files (the runs' presend.jsonl: '"ev":"presend_' lines +
run_start), rebuilds every LIVE position with its real realized P&L, and applies the frozen QUIET3 additions ON TOP of the live
config (today's QUIET skip and stop stay as they are):

  A  "unknown whale on a quiet token" (T2 windows only), at the arm:   v2.n_120s <= 15  AND  quiet.wh_dumps <= 3
       v2.n_120s     = the token's trades in the 120 s ring before the trigger (presend_live_arm "v2", dip23, already computed live)
       quiet.wh_dumps = the whale's dumps in the DumpBook's 24 h history closed before the trigger slot (presend_live_arm "quiet")
       (only when QUIET's arm rule is on: quiet.rule_on is not false, i.e. the DumpBook is warm)
  B  "creator nobody follows" (T2 and re-arm windows), at the arm: the creator (presend_live_arm ann.creator) has >= 1 of OUR OWN
     kept live positions that closed before the trigger time within the last 24 h, and ALL of its last <= 3 such positions were
     NOT FOLLOWED. A position is NOT FOLLOWED when no other wallet (not us, not the trigger whale, not the arm's holders) bought
     the token between our first buy and our last sell landing (chain order; presend_live_tape). A position is "closed" (its label
     known) at max(first buy t + 3 s, last sell landing t). Positions blocked by QUIET3 do not enter the history (the engine would
     not have traded them).

A blocked position SAVES exactly its realized P&L (presend_live_realized pnl). Money in SOL. Times PKT.
usage: quiet3_score.py [--warm FILE ...] [--cut NS] [--list] FILE [FILE ...]
  --warm: files read first in order to fill the creator history (not scored); FILEs are scored in the given order (history carries)
  --cut NS: also split the scored positions at trigger time NS (ns epoch) into "before"/"after"
  --list: print every blocked position"""
import sys, json, collections, datetime

A_N120, A_WHD = 15, 3
B_K, B_H_NS, B_FRAC = 3, 24 * 3600 * 10**9, 1.0
KNOWN_MIN_NS = 3 * 10**9

def pkt(ns): return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ns / 1e9, hours=5)).strftime('%m-%d %H:%M:%S')

def positions(fn):
    me = None
    arms = collections.defaultdict(list); closes = []; realized = collections.defaultdict(list); tape = collections.defaultdict(dict)
    for l in open(fn, errors='replace'):
        if '"ev":"presend_live_' not in l and '"ev":"run_start"' not in l: continue
        d = json.loads(l); ev = d['ev']
        if ev == 'run_start': me = me or d.get('wallet')
        elif ev == 'presend_live_arm':
            tr = d.get('trig') or d.get('dump') or {}
            arms[(d.get('mint') or tr.get('mint'), d.get('kind') or 'T2', d.get('w'))].append(d)
        elif ev == 'presend_live_close': closes.append(d)
        elif ev == 'presend_live_realized': realized[(d['mint'], d.get('pid'))].append(d)
        elif ev == 'presend_live_tape': tape[d['mint']][(d['slot'], d['idx'], d.get('j', 0))] = d
    used = collections.Counter(); out = []
    for c in closes:
        key = (c['mint'], c.get('pid')); rl = realized[key][used[key]] if used[key] < len(realized[key]) else None; used[key] += 1
        if rl is None: continue
        kind = c.get('kind') or 'T2'; b0 = min(c['buys'], key=lambda b: (b['slot'], b['idx']))
        arm = None
        for a in arms[(c['mint'], kind, c.get('w'))]:
            if ((a.get('trig') or a.get('dump') or {}).get('t') or 0) <= b0['t']: arm = a
        if arm is None: continue
        tr = arm.get('trig') or arm.get('dump') or {}
        excl = {me}
        if kind == 'T2' and tr.get('wallet'): excl.add(tr['wallet'])
        for h in arm.get('holders') or []: excl.add(h['w'])
        sl = c.get('sell_lands') or ([c['sell_land']] if c.get('sell_land') else [])
        endp = max(((x[0], x[1]) for x in sl), default=(b0['slot'] + 3, 1 << 30))
        sell_t = max((x[2] for x in sl if len(x) > 2 and x[2]), default=0)
        first = (b0['slot'], b0['idx'])
        fol = sum(1 for x in tape[c['mint']].values() if x['buy'] and x['user'] not in excl and first < (x['slot'], x['idx']) <= endp)
        out.append({'t0': tr.get('t') or b0['t'], 'buy_t': b0['t'], 'known': max(b0['t'] + KNOWN_MIN_NS, sell_t), 'mint': c['mint'], 'kind': kind,
                    'pnl': rl['pnl'] / 1e9, 'followed': fol > 0, 'creator': (arm.get('ann') or {}).get('creator'),
                    'n120': (arm.get('v2') or {}).get('n_120s'), 'whd': (arm.get('quiet') or {}).get('wh_dumps'),
                    'rule_on': (arm.get('quiet') or {}).get('rule_on')})
    out.sort(key=lambda p: p['t0'])
    return out

class Hist:
    def __init__(self): self.h = collections.defaultdict(list)
    def b_rule(self, p):
        if not p['creator']: return False
        prev = [q for q in self.h.get(p['creator'], []) if q['known'] < p['t0'] and q['known'] >= p['t0'] - B_H_NS]
        prev.sort(key=lambda q: q['known']); prev = prev[-B_K:]
        return len(prev) > 0 and sum(not q['followed'] for q in prev) >= B_FRAC * len(prev)
    def add(self, p):
        if p['creator']: self.h[p['creator']].append(p)

def a_rule(p): return (p['kind'] == 'T2' and p['n120'] is not None and p['whd'] is not None and p.get('rule_on') is not False
                       and p['n120'] <= A_N120 and p['whd'] <= A_WHD)

def run(files, hist, score):
    res = []
    for fn in files:
        ps = positions(fn)
        for p in ps:
            p['A'] = a_rule(p); p['B'] = hist.b_rule(p); p['blocked'] = p['A'] or p['B']; p['file'] = fn
            if not p['blocked']: hist.add(p)
        if score: res.extend(ps)
    return res

def table(name, ps):
    if not ps: print(f'{name:<22} no positions'); return
    span_d = max((max(p['buy_t'] for p in ps) - min(p['buy_t'] for p in ps)) / 86400e9, 1e-9)
    blk = [p for p in ps if p['blocked']]; kept = [p for p in ps if not p['blocked']]
    top5 = set(id(p) for p in sorted(ps, key=lambda p: -p['pnl'])[:5])
    net = sum(p['pnl'] for p in ps); save = -sum(p['pnl'] for p in blk)
    save5 = -sum(p['pnl'] for p in blk if id(p) not in top5); net5 = sum(p['pnl'] for p in ps if id(p) not in top5)
    w = lambda xs: (100.0 * sum(p['pnl'] > 0 for p in xs) / len(xs)) if xs else 0.0
    print(f'{name:<22} span {span_d * 24:5.1f} h | live n {len(ps):4d} net {net:+7.3f} win {w(ps):4.1f}% | blocked {len(blk):3d} (A {sum(p["A"] for p in blk):3d}, B-only {sum(p["B"] and not p["A"] for p in blk):3d}) '
          f'not-followed {sum(not p["followed"] for p in blk):3d} winners {sum(p["pnl"] > 0 for p in blk):3d} (+{sum(p["pnl"] for p in blk if p["pnl"] > 0):.3f}) '
          f'losers {sum(p["pnl"] <= 0 for p in blk):3d} ({sum(p["pnl"] for p in blk if p["pnl"] <= 0):+.3f}) | SAVES {save:+.3f} = {save / span_d:+.2f}/day '
          f'| kept net {net + save:+.3f} win {w(kept):4.1f}% | w/o top5: net {net5:+.3f} -> {net5 + save5:+.3f} (saves {save5:+.3f})')

if __name__ == '__main__':
    args = sys.argv[1:]; warm = []; files = []; cut = None; lst = False
    while args:
        a = args.pop(0)
        if a == '--warm':
            while args and not args[0].startswith('--'): warm.append(args.pop(0))
        elif a == '--cut': cut = int(args.pop(0))
        elif a == '--list': lst = True
        else: files.append(a)
    h = Hist(); run(warm, h, False); ps = run(files, h, True)
    print(f'QUIET3 on top of live: A = T2 & n_120s <= {A_N120} & wh_dumps <= {A_WHD}; B = creator: its last <= {B_K} kept positions in {B_H_NS // 3600e9:.0f} h all not followed')
    for fn in files: table(fn.split('/')[-1], [p for p in ps if p['file'] == fn])
    if cut is not None:
        table('before cut', [p for p in ps if p['t0'] < cut]); table('after cut', [p for p in ps if p['t0'] >= cut])
    table('ALL scored', ps)
    if lst:
        print('\nBLOCKED (time PKT of the trigger, kind, rule, mint, realized SOL, followed):')
        for p in ps:
            if p['blocked']: print(f"  {pkt(p['t0'])} {p['kind']:<5} {'A' if p['A'] else ' '}{'B' if p['B'] else ' '} {p['mint']} {p['pnl']:+.4f} {'followed' if p['followed'] else 'NOT followed'}")
