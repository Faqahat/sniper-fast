#!/usr/bin/env python3
# Enrich a population sample with same attributes as his_meta for comparison.
import json, sys, os, random
sys.path.insert(0,'/root/meta400')
import enrich_meta as e  # reuses rpc, fetch_uri, parse_mint, analyze_json

P=json.load(open('/root/profit_backtest/creates.json'))
random.seed(42)
# exclude his mints
HIS=set(x['mint'] for x in json.load(open('/root/last500/his_500.json')))
pool=[x for x in P if x['mint'] not in HIS]
random.shuffle(pool)
SAMPLE=pool[:300]

JSONL='/root/meta400/pop_meta.jsonl'
done=set()
if os.path.exists(JSONL):
    for line in open(JSONL):
        try: done.add(json.loads(line)['mint'])
        except: pass
f=open(JSONL,'a')
for i,t in enumerate(SAMPLE):
    mint=t['mint']
    if mint in done: continue
    rec={'mint':mint,'creator':t.get('creator'),'dev_buy':t.get('dev_buy'),
         'is_v2':t.get('is_v2'),'suffix':mint[-4:]}
    acct=e.rpc("getAccountInfo",[mint,{"encoding":"jsonParsed"}])
    rec.update(e.parse_mint(acct))
    uri=rec.get('onchain_uri')
    j,status=e.fetch_uri(uri)
    rec['uri_fetch_status']=status
    rec.update(e.analyze_json(j))
    f.write(json.dumps(rec)+'\n'); f.flush()
    if i%25==0: print(f"{i}/{len(SAMPLE)} {mint[:8]} {status[:14]}",file=sys.stderr,flush=True)
f.close()
recs=[json.loads(l) for l in open(JSONL)]
json.dump(recs,open('/root/meta400/pop_meta.json','w'))
print("DONE pop",len(recs),file=sys.stderr)
