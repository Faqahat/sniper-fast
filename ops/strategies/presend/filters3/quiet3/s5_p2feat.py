#!/usr/bin/env python3
"""QUIET3 step 5: per live position / shadow trigger, the token's recorded tape (s4_p2.py output) around the trigger:
  pre-trigger (chain position < the trigger trade): trades / unique buyers / unique sellers in the last 20/50/150 slots, slots since the
  previous trade, first slot seen; "bots" = wallets of BOTS.json (built from DEV backrun records only) that traded it before;
  post-trigger, per N = 1..6 (for a disarm decided when the slot clock reaches s0 + N: only slots <= s0 + N - 1 are complete, so the
  counts use slots s0 .. s0+N-1 after the trigger's position): other trades / buys / unique buyers / buy SOL (not whale, not us);
  labels (live only): any other buy within 10 slots after our first buy (fol10r), and within our hold.
Coverage: the trigger slot must lie inside the recording's span with >= 150 slots before and >= 12 after.
usage: s5_p2feat.py P2DIR OUTDIR BOTS.json"""
import sys, json, collections, glob, bisect
P2, OUT, BOTSF = sys.argv[1], sys.argv[2], sys.argv[3]
ME = 'EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR'
BOTS = set(json.load(open(BOTSF))['wallets'])          # 8-char prefixes
rows = {'trades': [json.loads(l) for l in open(f'{OUT}/trades.jsonl')], 'shadow': [json.loads(l) for l in open(f'{OUT}/shadow.jsonl')]}
need = collections.defaultdict(list)
for name, rs in rows.items():
    for k, r in enumerate(rs):
        need[r['mint']].append((name, k))
res = {name: [None] * len(rs) for name, rs in rows.items()}
for fn in sorted(glob.glob(f'{P2}/p2m_*.jsonl')):
    tape = collections.defaultdict(list); smin, smax = 1 << 62, 0
    for l in open(fn):
        d = json.loads(l)
        if d['tok'] == 0: continue
        tape[d['mint']].append((d['s'], d['i'] or 0, d['u'], d['tok'] > 0, abs(d['sol'])))
        smin = min(smin, d['s']); smax = max(smax, d['s'])
    print(fn, len(tape), smin, smax, flush=True)
    for m, tp in tape.items():
        tp.sort()
        keys = [(x[0], x[1]) for x in tp]
        for name, k in need.get(m, []):
            r = rows[name][k]
            if name == 'trades':
                s0, i0, whale = r.get('trig_slot'), None, r.get('whale')
            else:
                s0, i0, whale = r.get('slot'), None, r.get('whale')
            if s0 is None or not (smin + 150 <= s0 <= smax - 12): continue
            # the trigger trade's position: the whale's buy (T2) / the dump (rearm) in s0; else the start of s0
            wpos = [p for p in range(bisect.bisect_left(keys, (s0, -1)), bisect.bisect_left(keys, (s0 + 1, -1))) if tp[p][2] == whale]
            p0 = wpos[0] if wpos else bisect.bisect_left(keys, (s0, -1))
            f = {'p2': True, 'p2_found_trig': bool(wpos)}
            pre = tp[:p0]
            for N in (20, 50, 150):
                w = [x for x in pre if x[0] > s0 - N and x[2] != whale and x[2] != ME]
                f[f'p_tr{N}'] = len(w); f[f'p_ub{N}'] = len({x[2] for x in w if x[3]}); f[f'p_us{N}'] = len({x[2] for x in w if not x[3]})
                f[f'p_bs{N}'] = sum(x[4] for x in w if x[3]) / 1e9
            oth = [x for x in pre if x[2] != whale and x[2] != ME]
            f['p_last'] = s0 - oth[-1][0] if oth else 9999
            f['p_first'] = s0 - tp[0][0]
            f['p_bots'] = len({x[2][:8] for x in pre if x[2][:8] in BOTS})
            f['p_bots_buy'] = len({x[2][:8] for x in pre if x[3] and x[2][:8] in BOTS})
            post = [x for x in tp[p0 + 1:] if x[0] <= s0 + 12 and x[2] != whale and x[2] != ME]
            for N in range(1, 7):
                w = [x for x in post if x[0] <= s0 + N - 1]
                f[f'q_tr{N}'] = len(w); f[f'q_b{N}'] = sum(x[3] for x in w); f[f'q_ub{N}'] = len({x[2] for x in w if x[3]})
                f[f'q_bs{N}'] = sum(x[4] for x in w if x[3]) / 1e9; f[f'q_bot{N}'] = len({x[2][:8] for x in w if x[3] and x[2][:8] in BOTS})
            if name == 'trades':
                b = (r['slot'], r['idx'])
                af = [x for x in tp if (x[0], x[1]) > b and x[0] <= b[0] + 10 and x[2] != whale and x[2] != ME and x[3]]
                f['fol10r'] = len({x[2] for x in af}); f['fol10r_big'] = len({x[2] for x in af if x[4] >= 0.1e9})
                f['fol10r_bot'] = len({x[2][:8] for x in af if x[2][:8] in BOTS})
            res[name][k] = f
for name in rows:
    with open(f'{OUT}/{name}_p2.jsonl', 'w') as o:
        for f in res[name]: o.write(json.dumps(f or {'p2': False}) + '\n')
    print(name, sum(1 for f in res[name] if f), 'of', len(res[name]), 'covered', flush=True)
