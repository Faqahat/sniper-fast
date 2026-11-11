#!/usr/bin/env python3
"""dip47 FUNDER-CLUSTER log: the offline fixture of r83 w96 H2d2DtyD (the 17-wallet BufYjmzE team, 44% at our send) from the fix8283 study's
cached public-RPC responses (no network). Holders >= 0.5% at the send cutoff (state.json), per holder the two cached calls the study made
(getSignaturesForAddress before its first buy; getTransaction of the previous tx), trimmed to the fields the engine's parser reads.
usage: make_fixture.py [OUT]   (default testdata/dip47_funder_h2d2.json)"""
import json, hashlib, sys, os
D = '/home/it/sniper-data/fix8283/det'
def cached(method, params):
    key = hashlib.sha1(json.dumps([method, params], sort_keys=True).encode()).hexdigest()
    p = f'{D}/rpc/{key[:2]}/{key}.json'
    return json.load(open(p)).get('result') if os.path.exists(p) else None
S = json.load(open(f'{D}/state.json'))
s = [x for x in S if x['mint'].startswith('H2d2DtyD')][0]
out = {'mint': s['mint'], 'run': s['run'], 'w': s['w'], 'cut': s['cut'], 'holders': [], 'sigs': {}, 'tx': {}}
for h in s['hold']:
    if h['pct'] < 0.5 or not h['sig']: continue
    out['holders'].append({'w': h['w'], 'pct': h['pct'], 'first': h['first'], 'sig': h['sig']})
    r = cached('getSignaturesForAddress', [h['w'], {'before': h['sig'], 'limit': 8}])
    if r is None: continue
    out['sigs'][h['w'] + ':' + h['sig']] = [{'signature': x['signature'], 'slot': x['slot'], 'err': x.get('err')} for x in r[:2]]
    if not r: continue
    t = cached('getTransaction', [r[0]['signature'], {'encoding': 'jsonParsed', 'maxSupportedTransactionVersion': 1}])
    if not t: continue
    out['tx'][r[0]['signature']] = {'slot': t.get('slot'), 'transaction': {'message': {'accountKeys': [{'pubkey': a['pubkey'], 'signer': a.get('signer', False)} for a in t['transaction']['message']['accountKeys']]}},
                                    'meta': {'preBalances': t['meta']['preBalances'], 'postBalances': t['meta']['postBalances']}}
p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '../../testdata/dip47_funder_h2d2.json')
json.dump(out, open(p, 'w'), separators=(',', ':'))
print(len(out['holders']), 'holders', len(out['sigs']), 'sigs', len(out['tx']), 'txs ->', p, os.path.getsize(p), 'bytes')
