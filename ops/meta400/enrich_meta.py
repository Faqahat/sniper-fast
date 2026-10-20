#!/usr/bin/env python3
# Enrich his 409 mints with full on-chain mint attributes + metadata-uri JSON.
# Incremental: appends one JSON line per token to his_meta.jsonl, then builds his_meta.json.
import json, sys, os, time, re
import requests

ENV={}
for line in open('/root/sniper/deploy/.env'):
    line=line.strip()
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); ENV[k]=v
CK=ENV.get('CONSTANTK_TOKEN','')
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={CK}"

OUTDIR='/root/meta400'
JSONL=os.path.join(OUTDIR,'his_meta.jsonl')
OUTJSON=os.path.join(OUTDIR,'his_meta.json')

HIS=json.load(open('/root/last500/his_500.json'))

def rpc(method,params,tries=5):
    for i in range(tries):
        try:
            r=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":method,"params":params},timeout=30)
            j=r.json()
            if 'result' in j: return j['result']
        except Exception:
            pass
        time.sleep(0.6)
    return None

GW=['https://pump.mypinata.cloud/ipfs/','https://ipfs.io/ipfs/','https://dweb.link/ipfs/','https://nftstorage.link/ipfs/']
def fetch_uri(uri):
    if not uri: return None,'no_uri'
    # extract cid if ipfs
    cid=None
    m=re.search(r'/ipfs/([A-Za-z0-9]+)',uri)
    if m: cid=m.group(1)
    tried=[]
    urls=[]
    if cid:
        urls=[g+cid for g in GW]
    else:
        urls=[uri]
    for u in urls:
        for attempt in range(2):
            try:
                r=requests.get(u,timeout=18)
                if r.status_code==200:
                    try:
                        return r.json(),'ok:'+u.split('/ipfs/')[0]
                    except Exception:
                        # maybe text json
                        try: return json.loads(r.text),'ok_text:'+u
                        except Exception: tried.append(u+':badjson')
                else:
                    tried.append(u+':'+str(r.status_code))
                    break
            except Exception as e:
                tried.append(u+':err')
                time.sleep(0.4)
    return None,'FAIL:'+ ';'.join(tried[:4])

def parse_mint(acct):
    rec={'mint_program':None,'decimals':None,'supply':None,'mint_authority':None,
         'freeze_authority':None,'update_authority':None,'extensions':None,
         'onchain_name':None,'onchain_symbol':None,'onchain_uri':None,'acct_space':None}
    if not acct or not acct.get('value'):
        rec['_acct']='missing'; return rec
    val=acct['value']
    rec['mint_program']=val.get('owner')
    rec['acct_space']=val.get('space')
    data=val.get('data')
    if isinstance(data,dict) and 'parsed' in data:
        info=data['parsed'].get('info',{})
        rec['decimals']=info.get('decimals')
        rec['supply']=info.get('supply')
        rec['mint_authority']=info.get('mintAuthority')
        rec['freeze_authority']=info.get('freezeAuthority')
        exts=info.get('extensions')
        if exts:
            rec['extensions']=[e.get('extension') for e in exts]
            for e in exts:
                if e.get('extension')=='tokenMetadata':
                    st=e.get('state',{})
                    rec['onchain_name']=st.get('name')
                    rec['onchain_symbol']=st.get('symbol')
                    rec['onchain_uri']=st.get('uri')
                    rec['update_authority']=st.get('updateAuthority')
    return rec

SOCIAL_KEYS=['twitter','telegram','website','discord','coin_community','createdOn','image','description','name','symbol','showName','banner','video']

def analyze_json(j):
    out={'uri_keys':None,'uri_twitter':None,'uri_telegram':None,'uri_website':None,
         'uri_discord':None,'uri_createdOn':None,'uri_image':None,'uri_description':None,
         'uri_name':None,'uri_symbol':None,'uri_showName':None,'uri_has_social':None}
    if not isinstance(j,dict): return out
    out['uri_keys']=sorted(j.keys())
    low={k.lower():v for k,v in j.items()}
    out['uri_twitter']=low.get('twitter')
    out['uri_telegram']=low.get('telegram')
    out['uri_website']=low.get('website')
    out['uri_discord']=low.get('discord')
    out['uri_createdOn']=low.get('createdon')
    out['uri_image']=low.get('image')
    out['uri_description']=low.get('description')
    out['uri_name']=low.get('name')
    out['uri_symbol']=low.get('symbol')
    out['uri_showName']=low.get('showname')
    out['uri_has_social']=bool(out['uri_twitter'] or out['uri_telegram'] or out['uri_website'] or out['uri_discord'])
    return out

done=set()
if os.path.exists(JSONL):
    for line in open(JSONL):
        try: done.add(json.loads(line)['mint'])
        except Exception: pass

f=open(JSONL,'a')
n=len(HIS)
for i,t in enumerate(HIS):
    mint=t['mint']
    if mint in done:
        continue
    rec={'mint':mint,'create_slot':t.get('create_slot'),'his_buy_slot':t.get('his_buy_slot'),
         'creator':t.get('creator'),'bonding_curve':t.get('bonding_curve'),
         'dev_buy':t.get('dev_buy'),'dev_buy_wire':t.get('dev_buy_wire'),
         'jito_tip_create':t.get('jito_tip_create'),'is_v2':t.get('is_v2'),
         'name':t.get('name'),'symbol':t.get('symbol'),'uri':t.get('uri'),
         'has_image_pre':t.get('has_image'),'creator_fee_bps':t.get('creator_fee_bps'),
         'mayhem':t.get('mayhem'),'holder_reward':t.get('holder_reward'),
         'suffix':mint[-4:]}
    acct=rpc("getAccountInfo",[mint,{"encoding":"jsonParsed"}])
    rec.update(parse_mint(acct))
    uri=rec.get('onchain_uri') or t.get('uri')
    j,status=fetch_uri(uri)
    rec['uri_fetch_status']=status
    rec.update(analyze_json(j))
    f.write(json.dumps(rec)+'\n'); f.flush()
    if i%20==0:
        print(f"{i}/{n} {mint[:8]} prog={rec['mint_program'][-6:] if rec['mint_program'] else '?'} uri={status[:16]}",file=sys.stderr,flush=True)

f.close()
# build consolidated json
recs=[json.loads(l) for l in open(JSONL)]
json.dump(recs,open(OUTJSON,'w'),indent=0)
print(f"DONE: {len(recs)} records -> {OUTJSON}",file=sys.stderr)
