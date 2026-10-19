import requests, json, sys, time
RPC=open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EXACT="e1f7501ed5b38488"; CLASSIC="66063d1201daebea"; CREATE="d6904cec5f8b31b4"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,'big');pad=len(s)-len(s.lstrip('1'));return b'\x00'*pad+full
def b58e(b):
    n=int.from_bytes(b,'big');s=''
    while n>0:n,r=divmod(n,58);s=_A[r]+s
    return '1'*(len(b)-len(b.lstrip(b'\x00')))+s
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if 'result' in j and j['result'] is not None:return j['result']
            time.sleep(0.6)
        except:time.sleep(0.7)
    return None
def get_tx(sig):return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
def mint_sigs(mint,maxpages=16):
    out=[];before=None;pages=0
    while pages<maxpages:
        p=[mint,{"limit":1000}]
        if before:p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r:break
        out.extend(r);pages+=1
        if len(r)<1000:break
        before=r[-1]['signature']
    return out
def pump_ixs(tx):
    msg=tx['transaction']['message'];meta=tx.get('meta') or {}
    allix=list(msg.get('instructions',[]))
    for inr in meta.get('innerInstructions',[]):allix+=inr.get('instructions',[])
    res=[]
    for ix in allix:
        if ix.get('programId')!=PUMP:continue
        d=ix.get('data')
        if not d:continue
        try:raw=b58d(d)
        except:continue
        res.append((raw[:8].hex(),raw,ix))
    return res

E=json.load(open('/root/snipe_study50/enriched.json'))
recs=E['records']
fixed=0; stillbad=0; diag=[]
for rec in recs:
    if rec.get('create_found'): continue
    mint=rec['mint']; buyslot=rec['slot']
    sigs=mint_sigs(mint)
    if not sigs: stillbad+=1; continue
    min_slot=min(s['slot'] for s in sigs)
    cluster=[x for x in sigs if x['slot']==min_slot]
    ctx=None;cre=None;discs_seen=set()
    for s in cluster:  # ALL, no cap
        t=get_tx(s['signature'])
        if not t:continue
        pix=pump_ixs(t)
        for x in pix: discs_seen.add(x[0])
        c=[x for x in pix if x[0]==CREATE]
        if c: ctx=t;cre=c[0];break
    if cre is None:
        stillbad+=1
        diag.append((mint[:8],min_slot,buyslot,len(cluster),sorted(discs_seen)))
        continue
    cslot=ctx['slot'];rec['create_slot']=cslot;rec['delta']=buyslot-cslot;rec['create_found']=True
    rec['create_unreachable']=False
    raw=cre[1];off=8
    nl=int.from_bytes(raw[off:off+4],'little');off+=4+nl
    sl=int.from_bytes(raw[off:off+4],'little');off+=4+sl
    ul=int.from_bytes(raw[off:off+4],'little');off+=4+ul
    creator=raw[off:off+32];off+=32
    flags=raw[off:]
    rec['creator']=b58e(creator);rec['flags_hex']=flags.hex()
    rec['vanilla']=(len(flags)>0 and all(b==0 for b in flags))
    cre_accts=cre[2].get('accounts',[])
    bc=cre_accts[2] if len(cre_accts)>2 else None
    msg=ctx['transaction']['message'];meta=ctx['meta']
    keys=[a['pubkey'] for a in msg['accountKeys']]
    dev_buy=0
    if bc in keys:
        idx=keys.index(bc);dev_buy=meta['postBalances'][idx]-meta['preBalances'][idx]
    rec['dev_buy_lamports']=dev_buy
    def count_buyers(slot):
        buyers=set()
        for s in [x for x in sigs if x['slot']==slot and x.get('err') is None]:
            t=get_tx(s['signature'])
            if not t:continue
            for disc,r2,ix in pump_ixs(t):
                if disc==EXACT:
                    ac=ix.get('accounts',[])
                    if len(ac)>=9 and ac[8]!=WALLET:buyers.add(ac[8])
                elif disc==CLASSIC:
                    fp=t['transaction']['message']['accountKeys'][0]['pubkey']
                    if fp!=WALLET:buyers.add(fp)
        return len(buyers)
    rec['cosnipers_createslot']=count_buyers(cslot)
    rec['cosnipers_buyslot']=rec['cosnipers_createslot'] if buyslot==cslot else count_buyers(buyslot)
    fixed+=1
    print(f"FIXED {mint[:6]} d={rec['delta']} dev={dev_buy/1e9:.3f} van={rec['vanilla']} co={rec['cosnipers_createslot']}",file=sys.stderr)

json.dump(E,open('/root/snipe_study50/enriched.json','w'),indent=1)
print(f"\nfixed={fixed} stillbad={stillbad}",file=sys.stderr)
for d_ in diag[:15]: print("DIAG",d_,file=sys.stderr)
