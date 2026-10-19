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
            if 'result' in j:return j['result']
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
    return out,(pages>=maxpages and len(out)%1000==0)
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

d=json.load(open('/root/snipe_study50/snipes.json'))
snipes=d['snipes']
out=[]
for i,sn in enumerate(snipes):
    mint=sn['mint'];buyslot=sn['slot']
    rec=dict(sn)
    rec.update({'create_found':False,'delta':None,'dev_buy_lamports':None,'creator':None,
                'vanilla':None,'flags_hex':None,'cosnipers_createslot':None,'cosnipers_buyslot':None,
                'create_unreachable':False})
    sigs,capped=mint_sigs(mint)
    rec['mint_total_sigs']=len(sigs)
    if not sigs:
        out.append(rec);print(f"{i} {mint[:6]} NOSIGS",file=sys.stderr);continue
    min_slot=min(s['slot'] for s in sigs)
    # scan all sigs at min_slot for create_v2
    ctx=None;cre=None
    for s in [x for x in sigs if x['slot']==min_slot][:12]:
        t=get_tx(s['signature'])
        if not t:continue
        pix=pump_ixs(t)
        c=[x for x in pix if x[0]==CREATE]
        if c: ctx=t;cre=c[0];break
    if cre is None:
        rec['create_unreachable']=capped
        # outcome fields still: co-snipers at buy slot
        rec['cosnipers_buyslot']=None
        out.append(rec)
        print(f"{i} {mint[:6]} NO-CREATE capped={capped} minslot={min_slot} buyslot={buyslot} tot={len(sigs)}",file=sys.stderr)
        continue
    rec['create_found']=True
    cslot=ctx['slot'];rec['create_slot']=cslot;rec['delta']=buyslot-cslot
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
    rec['dev_buy_lamports']=dev_buy  # bonding-curve SOL delta at create = net dev buy (incl ~0.001 rent)
    def count_buyers(slot):
        buyers=set()
        for s in [x for x in sigs if x['slot']==slot and x.get('err') is None][:30]:
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
    rec['cosnipers_buyslot']=count_buyers(buyslot) if buyslot!=cslot else rec['cosnipers_createslot']
    out.append(rec)
    print(f"{i} {mint[:6]} d={rec['delta']} dev={dev_buy/1e9:.3f} van={rec['vanilla']} co_c={rec['cosnipers_createslot']} co_b={rec['cosnipers_buyslot']} tot={len(sigs)}",file=sys.stderr)

json.dump({"meta":{k:d[k] for k in ('n_sigs','n_succ','n_err','span','scanned')},"records":out},
          open('/root/snipe_study50/enriched.json','w'),indent=1)
print("DONE wrote enriched.json",file=sys.stderr)
