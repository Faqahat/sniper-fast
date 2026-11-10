#!/usr/bin/env python3
"""QUIET3 step 2: compact the observatory's backrun_sell records (every curve sell >= 1 SOL on a normal token and every buy on the
token in its slot + 2 slots; src/obs/backrun.rs) of one run's obs files -> one line per sell.
usage: s2_obs.py OUT.jsonl OBSFILE [OBSFILE ...]"""
import sys, json
out = open(sys.argv[1], 'w')
for fn in sys.argv[2:]:
    for l in open(fn, errors='replace'):
        if '"ev":"backrun_sell"' not in l: continue
        try: d = json.loads(l)
        except Exception: continue
        b = d.get('buys') or []
        out.write(json.dumps({'t': d['t'], 's': d['slot'], 'i': d['idx'], 'm': d['mint'], 'sol': d['sol'], 'drop': d.get('drop_pct'),
                              'seller': d.get('seller'), 'vsol': d.get('vsol'), 'age': d.get('age_slots'), 'nb': d.get('n_buys'),
                              'bsol': d.get('buy_sol'), 'b': [[x['w'], x['ds'], x['sol'], x.get('di')] for x in b],
                              'vs': d.get('v_sell'), 'vb': d.get('v_br'), 'part': d.get('partial')}, separators=(',', ':')) + '\n')
