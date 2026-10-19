import requests, json, sys, time

RPC = open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
FCDY = "FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BUY_DISC = "e1f7501ed5b38488"

_A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big')
    pad=len(s)-len(s.lstrip('1'))
    return b'\x00'*pad+full

def rpc(method, params, tries=5):
    for i in range(tries):
        try:
            r=requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=30)
            j=r.json()
            if 'result' in j: return j['result']
            if 'error' in j:
                err=j['error']
                if err.get('code')==-32019 or 'rate' in str(err).lower(): time.sleep(1.0); continue
                return None
        except Exception as e:
            time.sleep(0.8)
    return None

def get_sigs(addr, limit_total=2500):
    out=[]; before=None
    while len(out)<limit_total:
        p=[addr,{"limit":1000}]
        if before: p[1]["before"]=before
        res=rpc("getSignaturesForAddress",p)
        if not res: break
        out.extend(res)
        if len(res)<1000: break
        before=res[-1]['signature']
    return out

print("Listing wallet signatures...", file=sys.stderr)
sigs=get_sigs(WALLET, 2500)
print(f"total sigs: {len(sigs)}", file=sys.stderr)
succ=[s for s in sigs if s.get('err') is None]
err=[s for s in sigs if s.get('err') is not None]
print(f"success: {len(succ)}  error: {len(err)}", file=sys.stderr)

# time span
if sigs:
    bt=[s['blockTime'] for s in sigs if s.get('blockTime')]
    print(f"blockTime span: {min(bt)} .. {max(bt)}", file=sys.stderr)

def get_tx(sig):
    return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])

snipes=[]
scanned=0
for s in succ:
    if len(snipes)>=100: break
    sig=s['signature']
    tx=get_tx(sig)
    scanned+=1
    if not tx: continue
    meta=tx.get('meta') or {}
    msg=tx['transaction']['message']
    slot=tx['slot']
    bt=tx.get('blockTime')
    fee=meta.get('fee')
    # gather all instructions: top-level + inner
    allix=[]
    for ix in msg.get('instructions',[]): allix.append(ix)
    for inner in meta.get('innerInstructions',[]):
        for ix in inner.get('instructions',[]): allix.append(ix)
    found=None
    for ix in allix:
        if ix.get('programId')!=PUMP: continue
        data=ix.get('data')
        if not data: continue
        try: raw=b58d(data)
        except: continue
        if raw[:8].hex()!=BUY_DISC: continue
        accs=ix.get('accounts',[])
        if len(accs)<17: continue
        buyer=accs[8]; mint=accs[1]
        if buyer!=WALLET: continue
        qty=int.from_bytes(raw[8:16],'little')  # quote_amount_in lamports
        found={"mint":mint,"quote_lamports":qty}
        break
    if not found: continue
    # compute cu price from compute budget ix (programId ComputeBudget111...)
    cu_price=None; cu_limit=None
    CB="ComputeBudget111111111111111111111111111111"
    for ix in msg.get('instructions',[]):
        if ix.get('programId')==CB:
            d=ix.get('data')
            try: raw=b58d(d)
            except: continue
            if raw and raw[0]==3:  # SetComputeUnitPrice
                cu_price=int.from_bytes(raw[1:9],'little')
            elif raw and raw[0]==2:
                cu_limit=int.from_bytes(raw[1:5],'little')
    snipes.append({"sig":sig,"slot":slot,"blockTime":bt,"fee":fee,
                   "mint":found["mint"],"buy_lamports":found["quote_lamports"],
                   "cu_price":cu_price,"cu_limit":cu_limit})

print(f"scanned {scanned} success txs, found {len(snipes)} landed snipes", file=sys.stderr)
json.dump({"snipes":snipes,"n_sigs":len(sigs),"n_succ":len(succ),"n_err":len(err),
           "span":[min(s0['blockTime'] for s0 in sigs if s0.get('blockTime')),max(s0['blockTime'] for s0 in sigs if s0.get('blockTime'))],"scanned":scanned},
          open('/root/snipe_study50/snipes.json','w'), indent=1)
print("wrote snipes.json", file=sys.stderr)
