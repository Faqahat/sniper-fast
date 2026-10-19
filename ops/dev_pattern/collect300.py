import requests, json, sys, time
RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY_DISC="e1f7501ed5b38488"
CB="ComputeBudget111111111111111111111111111111"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big');pad=len(s)-len(s.lstrip('1'));return b'\x00'*pad+full
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if 'result' in j and j['result'] is not None:return j['result']
            if 'error' in j:
                e=j['error']
                if e.get('code')==-32019 or 'rate' in str(e).lower(): time.sleep(1.0); continue
            time.sleep(0.4)
        except: time.sleep(0.6)
    return None
def get_tx(sig):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])

# paginate all his sigs
out=[]; before=None
while len(out)<12000:
    p=[WALLET,{"limit":1000}]
    if before:p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if not r:break
    out.extend(r)
    if len(r)<1000:break
    before=r[-1]['signature']
print("total sigs",len(out),file=sys.stderr)
succ=[s for s in out if s.get('err') is None]
print("success",len(succ),file=sys.stderr)

snipes=[]; seen=set(); scanned=0
for s in succ:
    if len(snipes)>=300: break
    sig=s['signature']; tx=get_tx(sig); scanned+=1
    if not tx: continue
    meta=tx.get('meta') or {}; msg=tx['transaction']['message']
    allix=list(msg.get('instructions',[]))
    for inner in meta.get('innerInstructions',[]): allix+=inner.get('instructions',[])
    found=None
    for ix in allix:
        if ix.get('programId')!=PUMP: continue
        d=ix.get('data')
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex()!=BUY_DISC: continue
        accs=ix.get('accounts',[])
        if len(accs)<17: continue
        if accs[8]!=WALLET: continue
        found={"mint":accs[1],"quote_lamports":int.from_bytes(raw[8:16],'little')}
        break
    if not found: continue
    if found["mint"] in seen: continue   # one row per mint (first=latest landed buy)
    seen.add(found["mint"])
    cu_price=cu_limit=None
    for ix in msg.get('instructions',[]):
        if ix.get('programId')==CB:
            try: raw=b58d(ix.get('data'))
            except: continue
            if raw and raw[0]==3: cu_price=int.from_bytes(raw[1:9],'little')
            elif raw and raw[0]==2: cu_limit=int.from_bytes(raw[1:5],'little')
    snipes.append({"sig":sig,"slot":tx['slot'],"blockTime":tx.get('blockTime'),"fee":meta.get('fee'),
                   "mint":found["mint"],"buy_lamports":found["quote_lamports"],"cu_price":cu_price,"cu_limit":cu_limit})
    if len(snipes)%25==0: print("landed",len(snipes),"scanned",scanned,file=sys.stderr)

print("FINAL landed distinct mints",len(snipes),"scanned",scanned,file=sys.stderr)
json.dump({"snipes":snipes,"scanned":scanned,"n_sigs":len(out),
           "span":[min(s['blockTime'] for s in out if s.get('blockTime')),max(s['blockTime'] for s in out if s.get('blockTime'))]},
          open('/root/dev_pattern/snipes300.json','w'),indent=1)
print("wrote snipes300.json",file=sys.stderr)
