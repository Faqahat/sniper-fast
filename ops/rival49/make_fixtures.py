#!/usr/bin/env python3
"""dip49 test fixtures (no network):
 (1) testdata/dip49_9ye53.json: r85 w34 9Ye53E65 (fill slot 468340087): the failed slippage-type txs on the mint (rugdet fails_ours.parquet:
     err ':(6001|6002|6003|6042|6024|6040)$', our wallet out) in slots fill-30..fill, the rugdet slipsg20 and the dev age (report: 0.92 h)
 (2) testdata/dip49_f1_parity.json: r83-r85 fills: the fill annotation's holders (w, pct, n), the excluded set (trigger whale / dumper / R5
     holder) and rugdet's f1_pct / f1_n (feat_log.parquet) for the engine's f1_of parity test"""
import json, pickle, sys, pandas as pd
D = '/home/it/sniper-data/rugdet'; OURS = 'EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR'; OUT = sys.argv[1] if len(sys.argv) > 1 else 'testdata'
fa = pd.read_parquet(D + '/fails_ours.parquet')
for c in ('signer', 'mint', 'err'): fa[c] = fa[c].astype(str)
M = '9Ye53E65EHXNFygjNquFiLLNX6zYuooLUEQEffhRpump'; FS = 468340087
f = fa[(fa.mint == M) & (fa.signer != OURS) & (fa.s >= FS - 30) & (fa.s <= FS)]
slip = f[f.err.str.contains(r":(?:6001|6002|6003|6042|6024|6040)$")]
cut = FS - 2
sg20 = slip[(slip.s > cut - 20) & (slip.s <= cut)].signer.nunique()
json.dump({'mint': M, 'fill_slot': FS, 'sign_slot': FS - 1, 'slipsg20': int(sg20), 'dev_age_h': 0.92,
           'fails': [[int(r.s), r.signer, r.err] for r in f.itertuples()]}, open(OUT + '/dip49_9ye53.json', 'w'))
print('9Ye53E65: fails', len(f), 'slip', len(slip), 'slipsg20', sg20)
R = pickle.load(open(D + '/fillrecs.pkl', 'rb'))
F = pd.read_parquet(D + '/feat_log.parquet').set_index(['run', 'w'])
out = []
for d in R:
    if d['run'] < 83: continue
    f_, a = d['fill'], d.get('arm') or {}
    tr = a.get('trig') or a.get('dump') or {}
    whale = [x for x in [tr.get('wallet'), tr.get('seller'), (a.get('r5') or {}).get('holder')] if x]
    hs = (f_.get('ann') or {}).get('holders') or []
    k = (d['run'], d['w'])
    if k not in F.index: continue
    out.append({'run': d['run'], 'w': d['w'], 'kind': d['kind'], 'excl': whale, 'holders': [[h['w'], h['pct'], h['n']] for h in hs],
                'f1_pct': float(F.loc[k, 'f1_pct']), 'f1_n': int(F.loc[k, 'f1_n'])})
json.dump(out, open(OUT + '/dip49_f1_parity.json', 'w'), separators=(',', ':'))
print('f1 parity fills', len(out), 'rearm', sum(x['kind'] == 'rearm' for x in out))
